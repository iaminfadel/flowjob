"""Wiring checks for the run_pipeline adapter and the agent factory.

Thin on purpose — deep behaviour lives in engine tests; this file only
verifies the host adapter crosses the right seams.
"""

from unittest.mock import patch, MagicMock
from src.cli import build_agents
from src.pipeline.orchestrator import run_pipeline, SessionHealthError


def test_build_agents_creates_all_agents():
    with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test_key'}):
        agents = build_agents()
    assert "analyst" in agents
    assert "tailor" in agents
    assert "editor" in agents
    assert "applicator" in agents


def test_run_pipeline_health_probe_fires_before_any_work():
    """Session-health failure raises SessionHealthError before DB/stages run."""
    agents = {"analyst": MagicMock(), "tailor": MagicMock(), "editor": MagicMock(), "applicator": MagicMock()}
    with patch("src.pipeline.orchestrator.load_config") as mock_cfg, \
         patch("src.tools.browser.check_session_health", return_value=False), \
         patch("src.pipeline.orchestrator.init_db") as mock_init_db:
        mock_cfg.return_value.data.db_path = ":memory:"
        try:
            run_pipeline(agents, dry_run=True)
            raised = False
        except SessionHealthError:
            raised = True
        assert raised
        mock_init_db.assert_not_called()


def test_run_pipeline_dry_run_skips_applicator_stage():
    """dry_run=True never invokes the applicator even with a pending job."""
    from sqlmodel import Session, SQLModel, create_engine
    from src.db.models import Job, JobState
    from src.storage.document_store import InMemoryDocumentStore
    from src.config import FlowJobConfig

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="jd", state=JobState.PENDING_APPROVAL)
        session.add(job)
        session.commit()

        applicator = MagicMock()
        agents = {"analyst": MagicMock(), "tailor": MagicMock(), "editor": MagicMock(), "applicator": applicator}
        doc_store = InMemoryDocumentStore()

        with patch("src.tools.browser.check_session_health", return_value=True), \
             patch("src.pipeline.engine.scrape_linkedin_jobs", return_value=[]), \
             patch("src.pipeline.orchestrator.get_session") as mock_get_session, \
             patch("src.pipeline.orchestrator.load_config", return_value=FlowJobConfig()):
            mock_get_session.return_value.__enter__.return_value = session
            run_pipeline(agents, dry_run=True, doc_store=doc_store, approval_fn=lambda j: True)

        session.refresh(job)
        assert job.state == JobState.PENDING_APPROVAL
        applicator.run.assert_not_called()
