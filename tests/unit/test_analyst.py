import pytest
from unittest.mock import patch, MagicMock
from src.agents.analyst import AnalystAgent

class MockResponse:
    def __init__(self):
        from src.db.models import FitScore
        self.parsed = FitScore(
            score=90,
            matching_skills=["Python"],
            missing_skills=["Java"],
            recommendation="apply"
        )

@patch("src.agents.analyst.get_safe_resume_data")
def test_analyst_uses_injected_client(mock_safe_data):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MockResponse()
    
    mock_safe = MagicMock()
    mock_safe.model_dump.return_value = {"test": "data"}
    mock_safe_data.return_value = mock_safe
    
    agent = AnalystAgent(client=mock_client)
    result = agent.run({"jd_text": "Need Python dev"})
    
    assert result.score == 90
    assert result.recommendation == "apply"
    
    mock_client.models.generate_content.assert_called_once()
    call_args = mock_client.models.generate_content.call_args[1]
    assert "Need Python dev" in call_args["contents"]
