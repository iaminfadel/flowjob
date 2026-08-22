"""Edge-case stage transitions through the PipelineCycleEngine interface."""

import pytest
from unittest.mock import MagicMock
from sqlmodel import Session, SQLModel, create_engine
from src.db.models import Job, JobState
from src.pipeline.engine import PipelineCycleEngine
from src.storage.document_store import InMemoryDocumentStore


class FakeAgent:
    def __init__(self, name, should_fail=False):
        self.name = name
        self.should_fail = should_fail
        self.call_count = 0

    def run(self, *args, **kwargs):
        self.call_count += 1
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


def make_engine(agents):
    doc_store = InMemoryDocumentStore()
    return PipelineCycleEngine(
        config={"analyst": {"min_fit_score": 70}},
        agents=agents,
        doc_store=doc_store,
        approval_fn=lambda j: True,
        notify_fn=lambda t, m: None,
    )


def test_editor_retry_max_retries(session):
    """Editor failure path: ANALYZED with feedback recorded, then EDIT_FAIL."""
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.DRAFTED)
    session.add(job)
    session.commit()

    agents = {
        "analyst": FakeAgent("analyst"),
        "tailor": FakeAgent("tailor"),
        "editor": FakeAgent("editor", should_fail=True),
        "applicator": FakeAgent("applicator"),
    }
    eng = make_engine(agents)
    eng.doc_store.save_draft("1", {"basics": {"name": "Test"}})

    # Run 1: Editor fails -> feedback recorded, back to ANALYZED.
    # (process_analyzed_jobs runs before process_drafted_jobs in a cycle, so
    # the re-tailor lands on the NEXT cycle — same as production ordering.)
    assert eng.process_drafted_jobs(session) >= 0
    session.refresh(job)
    assert job.state == JobState.ANALYZED
    assert job.tailor_metadata["retries"] == 1
    assert job.tailor_metadata["feedback"] == "fix it"

    # Run 2: Tailor runs -> DRAFTED; Editor fails again -> EDIT_FAIL (max retries).
    assert eng.process_analyzed_jobs(session) >= 0
    assert eng.process_drafted_jobs(session) >= 0
    session.refresh(job)
    assert job.state == JobState.EDIT_FAIL


def test_approval_acceptance_invokes_applicator(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.PENDING_APPROVAL)
    session.add(job)
    session.commit()

    applicator = FakeAgent("applicator")
    eng = make_engine({"applicator": applicator})
    assert eng.process_pending_approval_jobs(session) >= 0

    session.refresh(job)
    assert job.state == JobState.APPLIED
    assert applicator.call_count == 1


def test_approval_rejection_transitions_to_skipped(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.PENDING_APPROVAL)
    session.add(job)
    session.commit()

    def reject(j):
        return False

    applicator = FakeAgent("applicator")
    eng = PipelineCycleEngine(
        config={},
        agents={"applicator": applicator},
        doc_store=InMemoryDocumentStore(),
        approval_fn=reject,
        notify_fn=lambda t, m: None,
    )
    assert eng.process_pending_approval_jobs(session) >= 0

    session.refresh(job)
    assert job.state == JobState.SKIPPED
    assert applicator.call_count == 0
