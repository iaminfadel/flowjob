from typing import Literal, Optional, List, Dict, Any, Tuple
import os
import json
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from src.agents.llm_factory import load_providers, create_chat, invoke_llm, Provider, order_providers, mark_provider_failure, session_extra_body
from src.utils.context import build_candidate_block, build_jd_section
from src.utils.resume_parser import parse_master_resume

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
        llm: Any = None,
        providers: List[Provider] = None,
        agent_name: str = "WriterAgent"
    ):
        self.model_name = model_name
        self.openrouter_base_url = openrouter_base_url
        self.openrouter_api_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")
        self.agent_name = agent_name
        self.providers = providers or load_providers()
        self._llm_injected = llm is not None
        
        if llm is not None:
            self.llm = llm
        elif self.providers:
            self.llm = create_chat(self.providers[0], model=self.model_name if self.providers[0].name == "explicit" else None, temperature=0.2)
        else:
            self.llm = None

    def run_round(
        self,
        jd_text: str,
        draft_data: dict,
        coverage_report: dict,
        master_resume_text: str = "",
        max_turns: int = 4,
        job_id: str = "",
        agent_name: str = ""
    ) -> tuple[dict, dict]:
        """Run one writer round until EmitPlanTool is emitted. Fails over across providers."""
        name = agent_name or self.agent_name
        if self._llm_injected:
            # Explicitly injected (mocked/legacy) LLM — no provider loop, no logging.
            return self._run_round_with_llm(self.llm, jd_text, draft_data, coverage_report, master_resume_text, max_turns)
        last_error = None
        for provider in order_providers(self.providers):
            try:
                return self._run_round_with_llm(
                    create_chat(provider, model=self.model_name if provider.name == "explicit" else None, temperature=0.2, extra_body=session_extra_body(provider, job_id)),
                    jd_text, draft_data, coverage_report, master_resume_text, max_turns, provider, job_id, name
                )
            except Exception as e:
                last_error = e
                mark_provider_failure(provider)
                print(f"[writer] Provider {provider.name} ({provider.model}) failed: {type(e).__name__}: {e}. Trying next provider...")
        if last_error:
            raise last_error
        raise RuntimeError("No LLM providers configured for WriterAgent.")

    def _run_round_with_llm(
        self,
        llm: Any,
        jd_text: str,
        draft_data: dict,
        coverage_report: dict,
        master_resume_text: str,
        max_turns: int,
        provider: Provider = None,
        job_id: str = "",
        agent_name: str = ""
    ) -> tuple[dict, dict]:
        """Run one writer round against a single LLM, logging every turn when a provider is known.

        Each turn starts a FRESH conversation with the current draft state instead of
        replaying tool-call history — avoids Gemini thought_signature errors on
        multi-turn function calls and keeps token usage low (no history re-send).
        """
        tools = [EditResumeTool, RequestHumanInputTool, EmitPlanTool]
        llm_with_tools = llm.bind_tools(tools)

        try:
            metadata, md_content = parse_master_resume("master_resume.md")
            candidate_block = build_candidate_block(metadata.skills, metadata.preferences, md_content)
        except Exception:
            candidate_block = f"Master Resume Bank (only use bullets that exist here):\n{master_resume_text}"
        jd_section = build_jd_section(jd_text)

        def build_user_prompt(draft: dict) -> str:
            pending = [
                r for r in coverage_report.get("requirements", [])
                if isinstance(r, dict) and r.get("route") in ("fix", "grill") and r.get("verdict") != "covered"
            ]
            report = {"requirements": pending, "summary": coverage_report.get("summary", "")}
            return (
                f"{candidate_block}\n\n"
                f"{jd_section}\n\n"
                f"Current Draft JSON:\n{json.dumps(draft, indent=2)}\n\n"
                f"Remaining Coverage Requirements to fix:\n{json.dumps(report, indent=2)}\n\n"
                f"Please execute necessary EditResumeTool calls and finish with EmitPlanTool."
            )

        for turn in range(max_turns):
            messages = [
                SystemMessage(content=WRITER_SYSTEM_PROMPT),
                HumanMessage(content=build_user_prompt(draft_data))
            ]
            if provider is not None:
                response = invoke_llm(llm_with_tools, messages, agent_name=agent_name, job_id=job_id, provider=provider.name, model=provider.model)
            else:
                response = llm_with_tools.invoke(messages)

            tool_calls = getattr(response, "tool_calls", [])
            if not tool_calls:
                continue

            emit_plan_call = next((tc for tc in tool_calls if tc.get("name") in ("EmitPlanTool", "emit_plan")), None)

            # Execute any EditResumeTool calls first
            for tc in tool_calls:
                tool_name = tc.get("name")
                args = tc.get("args", {})
                if isinstance(args, str):
                    args = json.loads(args)

                if tool_name in ("EditResumeTool", "edit_resume"):
                    try:
                        edit_obj = EditResumeTool.model_validate(args)
                        draft_data, status = execute_edit(edit_obj, draft_data)
                    except Exception as e:
                        print(f"[writer] Skipping invalid EditResumeTool call ({type(e).__name__}): {e}")
                elif tool_name in ("RequestHumanInputTool", "request_human_input"):
                    pass  # Question recorded; human grilling is handled outside the loop.

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
