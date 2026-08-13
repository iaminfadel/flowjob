import pytest
from pydantic import BaseModel
from google import genai
from unittest.mock import MagicMock
from src.agents.structured_llm import StructuredLLMAgent

class DummyResponse(BaseModel):
    result: str
    count: int

def test_structured_llm_formats_prompt_and_returns_schema():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = DummyResponse(result="success", count=42)
    mock_client.models.generate_content.return_value = mock_response

    agent = StructuredLLMAgent(
        client=mock_client,
        prompt_template="Hello {name}, you have {items} items.",
        response_schema=DummyResponse,
        temperature=0.5
    )

    result = agent.run({"name": "Alice", "items": 5})

    assert isinstance(result, DummyResponse)
    assert result.result == "success"
    assert result.count == 42
    
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["contents"] == "Hello Alice, you have 5 items."
    assert call_kwargs["config"].response_schema == DummyResponse
    assert call_kwargs["config"].temperature == 0.5

def test_structured_llm_preprocessors():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = DummyResponse(result="ok", count=1)
    mock_client.models.generate_content.return_value = mock_response

    def uppercase_name(ctx):
        ctx["name"] = ctx["name"].upper()
        return ctx

    agent = StructuredLLMAgent(
        client=mock_client,
        prompt_template="Name: {name}",
        response_schema=DummyResponse,
        preprocessors=[uppercase_name]
    )
    
    agent.run({"name": "bob"})
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["contents"] == "Name: BOB"

def test_structured_llm_retries_on_error():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = DummyResponse(result="retried", count=2)
    
    # Fail twice, succeed on third
    mock_client.models.generate_content.side_effect = [
        Exception("API Error 1"),
        Exception("API Error 2"),
        mock_response
    ]

    agent = StructuredLLMAgent(
        client=mock_client,
        prompt_template="Test",
        response_schema=DummyResponse
    )
    
    result = agent.run({})
    assert result.result == "retried"
    assert mock_client.models.generate_content.call_count == 3

def test_structured_llm_fails_after_retries():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API Error")

    agent = StructuredLLMAgent(
        client=mock_client,
        prompt_template="Test",
        response_schema=DummyResponse
    )
    
    with pytest.raises(Exception, match="API Error"):
        agent.run({})
        
    assert mock_client.models.generate_content.call_count == 3
