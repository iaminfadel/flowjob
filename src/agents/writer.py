from typing import Literal, Optional, List, Dict, Any, Tuple
import os
import json
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

class EditResumeTool(BaseModel):
    """Tool to edit draft resume JSON or master resume bank."""
    target: Literal["draft", "bank"] = Field(description="Target to edit: 'draft' or 'bank'")
    op: Literal["add", "replace", "remove"] = Field(description="Operation: 'add', 'replace', or 'remove'")
    section: str = Field(description="Section name (e.g. 'work', 'skills', 'summary', 'projects')")
    index: Optional[int] = Field(default=None, description="Index in list if applicable (e.g. work experience index)")
    tag: Optional[str] = Field(default=None, description="Optional bracket tag for bank bullets (e.g. '[k8s]')")
    content: str = Field(default="", description="The content or bullet to add/replace")

class RequestHumanInputTool(BaseModel):
    """Tool to flag a question for human input / grilling."""
    question: str = Field(description="The question to ask the candidate")
    context: str = Field(default="", description="Relevant requirement or gap context")

class EmitPlanTool(BaseModel):
    """Final tool called to emit the edit plan and conclude the writer round."""
    edits: list[dict] = Field(default_factory=list, description="Summary of edits performed")
    remaining: list[str] = Field(default_factory=list, description="Remaining uncovered requirements")
    needs_human: bool = Field(default=False, description="Whether human input is needed")
    summary: str = Field(default="", description="Summary of changes made this round")

def execute_edit(edit: EditResumeTool, draft_data: dict, master_resume_path: str = "master_resume.md") -> tuple[dict, str]:
    """Execute local mutation on draft JSON or master resume bank."""
    if edit.target == "draft":
        if edit.section == "summary":
            if edit.op in ("add", "replace"):
                draft_data["summary"] = edit.content
            elif edit.op == "remove":
                draft_data["summary"] = ""
            return draft_data, f"Draft summary updated ({edit.op})."

        elif edit.section == "skills":
            skills = draft_data.setdefault("skills", [])
            if edit.op == "add":
                if skills and isinstance(skills[0], dict):
                    target_group = next((g for g in skills if isinstance(g, dict) and g.get("category") == edit.tag), skills[0])
                    items = target_group.setdefault("items", [])
                    if edit.content not in items:
                        items.append(edit.content)
                else:
                    if edit.content not in skills:
                        skills.append(edit.content)
            elif edit.op == "remove":
                if edit.index is not None and 0 <= edit.index < len(skills):
                    skills.pop(edit.index)
                elif edit.content in skills:
                    skills.remove(edit.content)
            return draft_data, f"Draft skills updated ({edit.op})."

        elif edit.section in ("work", "experience"):
            work = draft_data.setdefault("work", [])
            idx = edit.index if edit.index is not None else 0
            if 0 <= idx < len(work):
                job = work[idx]
                highlights = job.setdefault("highlights", [])
                if edit.op == "add":
                    highlights.append(edit.content)
                elif edit.op == "replace" and len(highlights) > 0:
                    highlights[-1] = edit.content
                elif edit.op == "remove" and len(highlights) > 0:
                    highlights.pop()
                return draft_data, f"Draft work[{idx}] highlights updated ({edit.op})."
            elif edit.op == "add":
                work.append({"company": "Experience", "position": "Role", "highlights": [edit.content]})
                return draft_data, "New work entry added."
            else:
                return draft_data, f"Work index {idx} out of range."

        elif edit.section == "projects":
            projects = draft_data.setdefault("projects", [])
            if edit.op == "add":
                if edit.index is not None and 0 <= edit.index < len(projects):
                    projects[edit.index].setdefault("highlights", []).append(edit.content)
                else:
                    projects.append({"name": edit.content, "highlights": []})
            elif edit.op == "remove" and edit.index is not None and 0 <= edit.index < len(projects):
                projects.pop(edit.index)
            elif edit.op == "replace" and edit.index is not None and 0 <= edit.index < len(projects):
                projects[edit.index]["name"] = edit.content
            return draft_data, f"Draft projects updated ({edit.op})."

        return draft_data, f"Applied {edit.op} on draft section {edit.section}."

    elif edit.target == "bank":
        return draft_data, f"Bank updated with tag {edit.tag} in section {edit.section}."

    return draft_data, "Unknown edit target."

WRITER_SYSTEM_PROMPT = """You are an expert resume writer agent for FlowJob.
Your task is to improve the draft resume to address gaps identified in the coverage report using bullets from the master bank.

Available tools:
- EditResumeTool: Make concrete edits to draft resume (e.g. adding tailored bullet points to work highlights).
- RequestHumanInputTool: Ask candidate for specific evidence if missing from bank.
- EmitPlanTool: MUST ALWAYS be called to finish the round, summarizing the edits made and remaining gaps.
"""

class WriterAgent:
    def __init__(
        self,
        model_name: str = "google/gemini-2.5-pro",
        openrouter_base_url: str = "https://openrouter.ai/api/v1",
        openrouter_api_key: str = None,
        llm: Any = None
    ):
        self.model_name = model_name
        self.openrouter_base_url = openrouter_base_url
        self.openrouter_api_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")
        
        if llm is not None:
            self.llm = llm
        elif self.openrouter_api_key:
            self.llm = ChatOpenAI(
                model=self.model_name,
                api_key=self.openrouter_api_key,
                base_url=self.openrouter_base_url,
                temperature=0.2
            )
        else:
            self.llm = None

    def run_round(
        self,
        jd_text: str,
        draft_data: dict,
        coverage_report: dict,
        master_resume_text: str = "",
        max_turns: int = 4
    ) -> tuple[dict, dict]:
        """Run one writer round until EmitPlanTool is emitted."""
        tools = [EditResumeTool, RequestHumanInputTool, EmitPlanTool]
        llm_with_tools = self.llm.bind_tools(tools)
        
        user_prompt = (
            f"Job Description:\n{jd_text}\n\n"
            f"Current Draft JSON:\n{json.dumps(draft_data, indent=2)}\n\n"
            f"Coverage Report:\n{json.dumps(coverage_report, indent=2)}\n\n"
            f"Master Resume Bank:\n{master_resume_text}\n\n"
            f"Please execute necessary EditResumeTool calls and finish with EmitPlanTool."
        )
        
        messages = [
            SystemMessage(content=WRITER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        
        for turn in range(max_turns):
            response = llm_with_tools.invoke(messages)
            messages.append(response)
            
            tool_calls = getattr(response, "tool_calls", [])
            if not tool_calls:
                messages.append(HumanMessage(content="You did not call any tools. Please call EditResumeTool or EmitPlanTool."))
                continue
                
            emit_plan_call = next((tc for tc in tool_calls if tc.get("name") in ("EmitPlanTool", "emit_plan")), None)
            
            # Execute any EditResumeTool calls first
            for tc in tool_calls:
                tool_name = tc.get("name")
                args = tc.get("args", {})
                if isinstance(args, str):
                    args = json.loads(args)
                    
                if tool_name in ("EditResumeTool", "edit_resume"):
                    edit_obj = EditResumeTool.model_validate(args)
                    draft_data, status = execute_edit(edit_obj, draft_data)
                    tool_call_id = tc.get("id", f"call_{turn}")
                    messages.append(ToolMessage(tool_call_id=tool_call_id, content=status))
                elif tool_name in ("RequestHumanInputTool", "request_human_input"):
                    tool_call_id = tc.get("id", f"call_{turn}")
                    messages.append(ToolMessage(tool_call_id=tool_call_id, content="Question recorded."))
            
            if emit_plan_call:
                plan_args = emit_plan_call.get("args", {})
                if isinstance(plan_args, str):
                    plan_args = json.loads(plan_args)
                plan = EmitPlanTool.model_validate(plan_args)
                return draft_data, plan.model_dump()
                
        # If max turns reached without emit_plan, build fallback plan
        fallback_plan = EmitPlanTool(
            edits=[],
            remaining=[],
            needs_human=False,
            summary="Writer completed round (turn limit reached)."
        )
        return draft_data, fallback_plan.model_dump()
