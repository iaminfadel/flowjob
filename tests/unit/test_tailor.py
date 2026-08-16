import pytest
from unittest.mock import patch, MagicMock
from src.agents.tailor import TailorAgent

@patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test_key'})
@patch("src.agents.llm_factory.ChatOpenAI")
@patch("src.agents.tailor.get_safe_resume_data")
@patch("src.agents.tailor.parse_master_resume")
def test_tailor_returns_json(mock_parse_master, mock_safe_data, mock_chatopenai):
    mock_metadata = MagicMock()
    mock_metadata.name = "Alice"
    mock_metadata.email = "alice@example.com"
    mock_metadata.phone = "123"
    mock_metadata.location = "City, Region"
    mock_metadata.links = []
    mock_metadata.education = []
    
    mock_parse_master.return_value = (mock_metadata, "")
    
    agent = TailorAgent()
    mock_parsed_response = MagicMock()
    mock_parsed_response.model_dump.return_value = {"basics": {"name": "Bob"}}
    agent.structured_agent.run = MagicMock(return_value=mock_parsed_response)
    
    result = agent.run("JD")
    
    assert isinstance(result, dict)
    assert result["basics"]["name"] == "Alice" # PII injected
