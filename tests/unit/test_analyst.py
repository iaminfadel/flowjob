import pytest
from unittest.mock import patch, MagicMock
from src.agents.analyst import AnalystAgent
from src.db.models import FitScore

@patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test_key'})
@patch("src.agents.llm_factory.ChatOpenAI")
def test_analyst_agent(mock_chatopenai):
    agent = AnalystAgent()
    agent.run = MagicMock(return_value=FitScore(
        score=90,
        matching_skills=["Python"],
        missing_skills=["Java"],
        recommendation="apply"
    ))
    
    result = agent.run({"jd_text": "Need Python dev"})
    assert result.score == 90
    assert result.recommendation == "apply"
