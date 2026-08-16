import pytest
import os
from pydantic import BaseModel
from unittest.mock import MagicMock, patch
from src.agents.structured_llm import LangChainStructuredAgent

class DummyResponse(BaseModel):
    result: str
    count: int

@patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test_key'})
@patch('src.agents.llm_factory.ChatOpenAI')
def test_structured_llm_formats_prompt_and_returns_schema(mock_chatopenai):
    mock_llm_instance = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_llm_instance.bind_tools.return_value = mock_llm_with_tools
    mock_chatopenai.return_value = mock_llm_instance
    
    mock_response = MagicMock()
    mock_response.tool_calls = [{"name": "DummyResponse", "args": {"result": "success", "count": 42}}]
    mock_llm_with_tools.invoke.return_value = mock_response
    
    agent = LangChainStructuredAgent(
        prompt_template="Hello {name}, you have {items} items.",
        response_schema=DummyResponse,
        temperature=0.5
    )

    result = agent.run({"name": "Alice", "items": 5})

    assert isinstance(result, DummyResponse)
    assert result.result == "success"
    assert result.count == 42
    mock_llm_instance.bind_tools.assert_called_once_with([DummyResponse])
    mock_llm_with_tools.invoke.assert_called_once_with(["Hello Alice, you have 5 items."])


from src.agents.structured_llm import invoke_with_schema_tool, SchemaExtractionError

def test_invoke_with_schema_tool_success():
    class DummySchema(BaseModel):
        foo: str
        bar: int
        
    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools
    
    mock_response = MagicMock()
    mock_response.tool_calls = [{"name": "DummySchema", "args": {"foo": "test", "bar": 123}}]
    mock_llm_with_tools.invoke.return_value = mock_response
    
    result = invoke_with_schema_tool(mock_llm, ["hello"], DummySchema)
    
    assert isinstance(result, DummySchema)
    assert result.foo == "test"
    assert result.bar == 123
    mock_llm.bind_tools.assert_called_once_with([DummySchema])
    mock_llm_with_tools.invoke.assert_called_once_with(["hello"])

def test_invoke_with_schema_tool_fallback_name():
    class DummySchema(BaseModel):
        foo: str
        
    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools
    
    mock_response = MagicMock()
    mock_response.tool_calls = [{"name": "WrongName", "args": {"foo": "test2"}}]
    mock_llm_with_tools.invoke.return_value = mock_response
    
    result = invoke_with_schema_tool(mock_llm, ["hello"], DummySchema)
    
    assert isinstance(result, DummySchema)
    assert result.foo == "test2"

def test_invoke_with_schema_tool_retry_on_text():
    class DummySchema(BaseModel):
        foo: str
        
    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools
    
    mock_response_fail = MagicMock()
    mock_response_fail.tool_calls = []
    
    mock_response_success = MagicMock()
    mock_response_success.tool_calls = [{"name": "DummySchema", "args": {"foo": "test3"}}]
    
    mock_llm_with_tools.invoke.side_effect = [mock_response_fail, mock_response_success]
    
    result = invoke_with_schema_tool(mock_llm, ["hello"], DummySchema)
    
    assert result.foo == "test3"
    assert mock_llm_with_tools.invoke.call_count == 2

def test_invoke_with_schema_tool_fails_after_retries():
    class DummySchema(BaseModel):
        foo: str
        
    mock_llm = MagicMock()
    mock_llm_with_tools = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm_with_tools
    
    mock_response_fail = MagicMock()
    mock_response_fail.tool_calls = []
    
    mock_llm_with_tools.invoke.return_value = mock_response_fail
    
    with pytest.raises(SchemaExtractionError, match="Model returned text but failed to call the expected tool."):
        invoke_with_schema_tool(mock_llm, ["hello"], DummySchema, retries=2)
        
    assert mock_llm_with_tools.invoke.call_count == 2

