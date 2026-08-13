import pytest
from unittest.mock import patch, MagicMock
from src.cli import build_agents
from src.pipeline.orchestrator import run_pipeline

@patch("google.genai.Client")
def test_build_agents_creates_all_agents(mock_client):
    agents = build_agents()
    assert "analyst" in agents
    assert "tailor" in agents
    assert "editor" in agents
    assert "applicator" in agents

@patch("src.pipeline.orchestrator.init_db")
@patch("src.pipeline.orchestrator.get_session")
@patch("src.tools.browser.check_session_health")
@patch("builtins.open")
@patch("src.pipeline.orchestrator.yaml.safe_load")
@patch("src.utils.resume_parser.parse_master_resume")
@patch("os.path.exists")
def test_run_pipeline_wiring(mock_exists, mock_parse_master, mock_yaml_load, mock_open, mock_check_session, mock_get_session, mock_init_db):
    mock_check_session.return_value = True
    mock_yaml_load.return_value = {"data": {"db_path": ":memory:"}}
    
    mock_metadata = MagicMock()
    mock_parse_master.return_value = (mock_metadata, "")
    
    mock_exists.return_value = True
    
    mock_session = MagicMock()
    # Return empty list for all queries to not do any work
    mock_session.exec.return_value.all.return_value = []
    
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_session
    mock_get_session.return_value = mock_context_manager
    
    agents = {
        "analyst": MagicMock(),
        "tailor": MagicMock(),
        "editor": MagicMock(),
        "applicator": MagicMock(),
    }
    
    # Run the pipeline with dry_run to not call the applicator
    run_pipeline(agents=agents, dry_run=True)
    
    mock_init_db.assert_called_once()
    mock_get_session.assert_called_once()
