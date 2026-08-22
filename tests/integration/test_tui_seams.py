"""run_pipeline adapter tests: host concerns (config, DB wiring, health probe).

Mocks only at true external seams (browser health probe). DB is real
in-memory SQLite; agents are fakes.
"""

import pytest
from unittest.mock import patch, MagicMock
from sqlmodel import Session, SQLModel, create_engine
from src.db.models import Job, JobState
from src.pipeline.orchestrator import run_pipeline
from src.pipeline.types import SessionHealthError


class FakeAgent:
    def __init__(self, name, should_fail=False):
        self.name = name
        self.should_fail = should_fail
        self.call_count = 0
        self.last_wait_fn = None

    def run(self, *args, **kwargs):
        self.call_count += 1
        self.last_wait_fn = args[1] if len(args) > 1 else kwargs.get("wait_fn")
        if self.name == "editor":
            class EditScore:
                passed = not self.should_fail
                score = 95
                feedback = "fix it"
            return EditScore()
        elif self.name == "tailor":
            return {"basics": {"name": "Test"}}
        elif self.name == "analyst":
            class FitScore:
                score = 80
                recommendation = "apply"
            return FitScore()
        elif self.name == "applicator":
            return not self.should_fail


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def make_agents():
    return {
        "analyst": FakeAgent("analyst"),
        "tailor": FakeAgent("tailor"),
        "editor": FakeAgent("editor"),
        "applicator": FakeAgent("applicator"),
    }


def run_pipeline_with(session, agents, **kwargs):
    with patch("src.tools.browser.check_session_health", return_value=True), \
         patch("src.pipeline.engine.scrape_linkedin_jobs", return_value=[]), \
         patch("src.pipeline.engine.scrape_linkedin_jobs", return_value=[]) as _scout, \
         patch("src.pipeline.orchestrator.get_session") as mock_get_session:
        mock_get_session.return_value.__enter__.return_value = session
        kwargs.setdefault("config_path", "/nonexistent/flowjob.yaml")
        # config_path load is bypassed by passing a full config dict via db_path trick —
        # instead patch load_config to hand back a minimal valid config.
        from src.config import FlowJobConfig
        with patch("src.pipeline.orchestrator.load_config", return_value=FlowJobConfig()):
            kwargs.pop("config_path", None)
            kwargs.setdefault("db_path", ":memory:")
            return run_pipeline(agents, dry_run=False, **kwargs)


def test_approval_fn_is_invoked_with_job_and_accepts(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.PENDING_APPROVAL)
    session.add(job)
    session.commit()

    calls = []
    def approval_fn(j):
        calls.append(j)
        return True

    agents = make_agents()
    run_pipeline_with(session, agents, approval_fn=approval_fn)

    session.refresh(job)
    assert len(calls) == 1
    assert calls[0].id == job.id
    assert job.state == JobState.APPLIED
    assert agents["applicator"].call_count == 1


def test_approval_fn_rejection_transitions_to_skipped(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.PENDING_APPROVAL)
    session.add(job)
    session.commit()

    def approval_fn(j):
        return False

    agents = make_agents()
    run_pipeline_with(session, agents, approval_fn=approval_fn)

    session.refresh(job)
    assert job.state == JobState.SKIPPED
    assert agents["applicator"].call_count == 0


def test_approval_fn_defaults_to_stdin_gate(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.PENDING_APPROVAL)
    session.add(job)
    session.commit()

    with patch("src.pipeline.orchestrator.prompt_user_approval", return_value=True) as mock_gate:
        agents = make_agents()
        run_pipeline_with(session, agents)

    session.refresh(job)
    assert mock_gate.call_count == 1
    assert job.state == JobState.APPLIED


def test_wait_fn_is_threaded_to_applicator(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.PENDING_APPROVAL)
    session.add(job)
    session.commit()

    recorded = []
    def wait_fn(prompt):
        recorded.append(prompt)

    agents = make_agents()
    run_pipeline_with(session, agents, approval_fn=lambda j: True, wait_fn=wait_fn)

    assert agents["applicator"].call_count == 1
    assert agents["applicator"].last_wait_fn is wait_fn
    assert job.state == JobState.APPLIED


def test_wait_fn_defaults_to_none(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.PENDING_APPROVAL)
    session.add(job)
    session.commit()

    agents = make_agents()
    summary = run_pipeline_with(session, agents, approval_fn=lambda j: True)

    assert agents["applicator"].last_wait_fn is None
    assert summary.duration_s >= 0


def test_run_pipeline_returns_cycle_summary_with_counts(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.PENDING_APPROVAL)
    session.add(job)
    session.commit()

    agents = make_agents()
    summary = run_pipeline_with(session, agents, approval_fn=lambda j: True)

    session.refresh(job)
    assert summary.jobs_applied == 1
    assert summary.counts_delta.get("APPLIED") == 1
    assert summary.halted_reason is None


def test_session_health_failure_raises_instead_of_sys_exit(session):
    agents = make_agents()
    with patch("src.pipeline.orchestrator.load_config"), \
         patch("src.tools.browser.check_session_health", return_value=False):
        with pytest.raises(SessionHealthError):
            run_pipeline(agents, dry_run=False)


def test_editor_retry_max_retries(session):
    """Editor failure path: ANALYZED with feedback, then EDIT_FAIL on retry."""
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.DRAFTED)
    session.add(job)
    session.commit()

    agents = {
        "analyst": FakeAgent("analyst"),
        "tailor": FakeAgent("tailor"),
        "editor": FakeAgent("editor", should_fail=True),
        "applicator": FakeAgent("applicator"),
    }

    from src.storage.document_store import InMemoryDocumentStore

    doc_store = InMemoryDocumentStore()
    doc_store.save_draft("1", {"basics": {"name": "Test"}})

    with patch("src.tools.browser.check_session_health", return_value=True), \
         patch("src.pipeline.engine.scrape_linkedin_jobs", return_value=[]), \
         patch("src.pipeline.orchestrator.get_session") as mock_get_session, \
         patch("src.pipeline.orchestrator.load_config", return_value=MagicMock(model_dump=lambda: {}, data=MagicMock(db_path=":memory:"))):
        mock_get_session.return_value.__enter__.return_value = session

        # Run 1: Editor fails -> feedback recorded, back to ANALYZED.
        run_pipeline(agents, dry_run=False, doc_store=doc_store, approval_fn=lambda j: True)
        session.refresh(job)
        assert job.state == JobState.ANALYZED
        assert job.tailor_metadata["retries"] == 1
        assert job.tailor_metadata["feedback"] == "fix it"

        # Run 2: Tailor runs -> DRAFTED; Editor fails again -> EDIT_FAIL (max retries).
        run_pipeline(agents, dry_run=False, doc_store=doc_store, approval_fn=lambda j: True)
        session.refresh(job)
        assert job.state == JobState.EDIT_FAIL
