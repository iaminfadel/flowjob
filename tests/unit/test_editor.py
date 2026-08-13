import pytest
from unittest.mock import patch, MagicMock
from src.agents.editor import EditorAgent

class MockResponse:
    def __init__(self):
        from src.agents.editor import EditorScore
        self.parsed = EditorScore(
            score=85,
            passed=True,
            feedback=""
        )

@patch("src.agents.editor.extract_text_from_pdf")
@patch("src.agents.editor.get_safe_resume_data")
def test_editor_uses_injected_client(mock_safe_data, mock_extract_text):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MockResponse()
    
    mock_safe = MagicMock()
    mock_safe.model_dump_json.return_value = "{}"
    mock_safe_data.return_value = mock_safe
    
    mock_extract_text.return_value = "Extracted text"
    
    agent = EditorAgent(client=mock_client)
    result = agent.run({"jd_text": "Need Java dev", "pdf_path": "fake.pdf"})
    
    assert result.score == 85
    assert result.passed is True
    
    mock_client.models.generate_content.assert_called_once()
    call_args = mock_client.models.generate_content.call_args[1]
    assert "Need Java dev" in call_args["contents"]
    assert "Extracted text" in call_args["contents"]
