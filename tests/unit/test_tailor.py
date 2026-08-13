import pytest
from unittest.mock import patch, MagicMock
from src.agents.tailor import TailorAgent, ResumeOutput, Basics

class MockParsed:
    def model_dump(self):
        return {"basics": {"name": "Bob"}}

class MockResponse:
    def __init__(self):
        self.parsed = MockParsed()

@patch("src.agents.tailor.get_safe_resume_data")
@patch("src.agents.tailor.parse_master_resume")
def test_tailor_returns_json(mock_parse_master, mock_safe_data):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MockResponse()
    
    mock_safe = MagicMock()
    mock_safe.model_dump_json.return_value = "{}"
    mock_safe_data.return_value = mock_safe
    
    mock_metadata = MagicMock()
    mock_metadata.name = "Alice"
    mock_metadata.email = "alice@example.com"
    mock_metadata.phone = "123"
    mock_metadata.location = "City, Region"
    mock_metadata.links = []
    mock_metadata.education = []
    
    mock_parse_master.return_value = (mock_metadata, "")
    
    agent = TailorAgent(client=mock_client)
    result = agent.run("JD")
    
    assert isinstance(result, dict)
    assert result["basics"]["name"] == "Alice" # PII injected
    mock_client.models.generate_content.assert_called_once()
    
    # Prompt check
    call_args = mock_client.models.generate_content.call_args[1]
    assert "JD" in call_args["contents"]
