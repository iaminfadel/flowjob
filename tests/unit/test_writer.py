import pytest
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage
from src.agents.writer import (
    EditResumeTool,
    RequestHumanInputTool,
    EmitPlanTool,
    execute_edit,
    WriterAgent
)

def test_execute_edit_draft_summary():
    draft = {"summary": "Old summary"}
    tool = EditResumeTool(
        target="draft",
        op="replace",
        section="summary",
        content="New senior engineering summary"
    )
    draft, msg = execute_edit(tool, draft)
    assert draft["summary"] == "New senior engineering summary"
    assert "updated" in msg

def test_execute_edit_draft_work_highlights():
    draft = {
        "work": [
            {"company": "Acme", "highlights": ["Built backend in Go"]}
        ]
    }
    tool = EditResumeTool(
        target="draft",
        op="add",
        section="work",
        index=0,
        content="Optimized PostgreSQL queries reducing latency by 40%."
    )
    draft, msg = execute_edit(tool, draft)
    assert len(draft["work"][0]["highlights"]) == 2
    assert "Optimized PostgreSQL queries" in draft["work"][0]["highlights"][1]

def test_execute_edit_draft_skills_category_dicts():
    draft = {
        "skills": [
            {"category": "Tools", "items": ["Docker"]},
            {"category": "Languages", "items": ["Python"]}
        ]
    }
    tool = EditResumeTool(
        target="draft",
        op="add",
        section="skills",
        tag="Tools",
        content="Kubernetes"
    )
    draft, msg = execute_edit(tool, draft)
    assert "Kubernetes" in draft["skills"][0]["items"]

def test_execute_edit_draft_projects():
    draft = {
        "projects": [
            {"name": "FlowJob", "highlights": ["Built CLI"]}
        ]
    }
    tool = EditResumeTool(
        target="draft",
        op="add",
        section="projects",
        index=0,
        content="Integrated AI Agents"
    )
    draft, msg = execute_edit(tool, draft)
    assert "Integrated AI Agents" in draft["projects"][0]["highlights"]

def test_writer_agent_run_round_with_mock_llm():
    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools

    # 1st response: calls EditResumeTool + EmitPlanTool
    mock_ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "EditResumeTool",
                "args": {
                    "target": "draft",
                    "op": "add",
                    "section": "work",
                    "index": 0,
                    "content": "Added K8s bullet from bank."
                },
                "id": "call_1"
            },
            {
                "name": "EmitPlanTool",
                "args": {
                    "edits": [{"section": "work", "action": "add"}],
                    "remaining": [],
                    "needs_human": False,
                    "summary": "Added K8s bullet to experience."
                },
                "id": "call_2"
            }
        ]
    )
    mock_llm_with_tools.invoke.return_value = mock_ai_msg

    agent = WriterAgent(llm=mock_llm)
    draft = {"work": [{"company": "Tech Corp", "highlights": []}]}
    coverage = {"requirements": [{"requirement": "Kubernetes", "route": "fix"}]}

    updated_draft, plan = agent.run_round(
        jd_text="Need K8s expert",
        draft_data=draft,
        coverage_report=coverage,
        master_resume_text="[k8s] Scaled 500 pods."
    )

    assert len(updated_draft["work"][0]["highlights"]) == 1
    assert "Added K8s bullet" in updated_draft["work"][0]["highlights"][0]
    assert plan["summary"] == "Added K8s bullet to experience."
    assert not plan["needs_human"]
