"""Full-cycle behaviour through run_pipeline: NEW job -> APPLIED, one seam-mocked browser."""

from unittest.mock import patch, MagicMock
from sqlmodel import Session, SQLModel, create_engine
from src.db.models import Job, JobState
from src.pipeline.orchestrator import run_pipeline
from src.storage.document_store import InMemoryDocumentStore
from src.config import FlowJobConfig


class FakeAgent:
    def __init__(self, name):
        self.name = name

    def run(self, *args, **kwargs):
        if self.name == "analyst":
            class FitScore:
                score = 80
                recommendation = "apply"
            return FitScore()
        elif self.name == "tailor":
            return {"basics": {"name": "Test"}}
        elif self.name == "editor":
            class EditScore:
                passed = True
                score = 95
                feedback = []
            return EditScore()
        elif self.name == "applicator":
            return True


def test_full_pipeline_sequence():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.NEW)
        session.add(job)
        session.commit()

        doc_store = InMemoryDocumentStore()
        agents = {
            "analyst": FakeAgent("analyst"),
            "tailor": FakeAgent("tailor"),
            "editor": FakeAgent("editor"),
            "applicator": FakeAgent("applicator"),
        }

        with patch("src.tools.browser.check_session_health", return_value=True), \
             patch("src.pipeline.engine.scrape_linkedin_jobs", return_value=[]) as mock_scout, \
             patch("src.pipeline.orchestrator.get_session") as mock_get_session, \
             patch("src.pipeline.orchestrator.load_config", return_value=FlowJobConfig()):
            mock_get_session.return_value.__enter__.return_value = session
            summary = run_pipeline(agents, dry_run=False, doc_store=doc_store, approval_fn=lambda j: True)

        session.refresh(job)
        assert job.state == JobState.APPLIED
        assert summary.jobs_applied == 1
        assert mock_scout.call_count >= 1  # one call per built query from master_resume preferences
