import pytest
from unittest.mock import MagicMock, patch
from src.agents.coverage_critic import (
    RequirementCheck,
    CoverageReport,
    CoverageCriticAgent,
    critic_preprocessor
)

def test_coverage_report_schema():
    report = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="5+ years Python",
                must_have=True,
                verdict="covered",
                route="drop",
                support=["Led Python backend engineering"]
            ),
            RequirementCheck(
                requirement="Kubernetes",
                must_have=True,
                verdict="missing",
                route="fix",
                support=[]
            ),
            RequirementCheck(
                requirement="GraphQL",
                must_have=False,
                verdict="missing",
                route="drop",
                support=[]
            )
        ],
        summary="Good match, need K8s bullet from bank."
    )
    assert not report.unfixable
    assert len(report.requirements) == 3
    assert report.requirements[1].route == "fix"

def test_critic_preprocessor():
    draft_data = {
        "basics": {"name": "Test Engineer"},
        "skills": [{"category": "Languages", "items": ["Python"]}]
    }
    context = {"draft_data": draft_data}
    processed = critic_preprocessor(context)
    assert "draft_markdown" in processed
    assert "# Test Engineer" in processed["draft_markdown"]

@patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test_key'})
@patch('src.agents.llm_factory.ChatOpenAI')
def test_coverage_critic_agent_run(mock_chatopenai):
    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools
    mock_chatopenai.return_value = mock_llm
    
    mock_response = MagicMock()
    mock_response.tool_calls = [{
        "name": "CoverageReport",
        "args": {
            "unfixable": False,
            "requirements": [
                {
                    "requirement": "PostgreSQL",
                    "must_have": True,
                    "verdict": "missing",
                    "route": "grill",
                    "support": [],
                    "note": "Need to ask candidate about Postgres experience"
                }
            ],
            "summary": "1 gap needing grilling"
        }
    }]
    mock_llm_with_tools.invoke.return_value = mock_response

    agent = CoverageCriticAgent()
    res = agent.run({
        "jd_text": "Must know PostgreSQL",
        "draft_markdown": "# Dev",
        "bank_bullets": "- Python Dev"
    })

    assert isinstance(res, CoverageReport)
    assert not res.unfixable
    assert len(res.requirements) == 1
    assert res.requirements[0].route == "grill"
