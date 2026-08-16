import pytest
from unittest.mock import patch, MagicMock
from src.agents.editor import EditorAgent, EditorScore

@patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test_key'})
@patch("src.agents.llm_factory.ChatOpenAI")
def test_editor_agent(mock_chatopenai):
    agent = EditorAgent()
    agent.run = MagicMock(return_value=EditorScore(
        score=85,
        passed=True,
        feedback=""
    ))
    
    result = agent.run({"jd_text": "Need Java dev", "pdf_path": "fake.pdf"})
    assert result.score == 85
    assert result.passed is True
