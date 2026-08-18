import pytest
from unittest.mock import MagicMock
from sqlmodel import Session, SQLModel, create_engine, select
from src.db.models import Job, JobState, ErrorRecord, FitScore
from src.pipeline.engine import PipelineCycleEngine, CycleSummaryResult
from src.storage.document_store import InMemoryDocumentStore


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_engine_analyst_stage_success(session):
    job = Job(
        id="job1",
        title="Software Engineer",
        company="TechCorp",
        url="http://test.com",
        location="Remote",
        posted_date="today",
        jd_text="Python engineer required",
        state=JobState.NEW,
    )
    session.add(job)
    session.commit()

    analyst_mock = MagicMock()
    analyst_mock.run.return_value = FitScore(
        score=85,
        matching_skills=["Python"],
        missing_skills=[],
        recommendation="apply",
    )

    doc_store = InMemoryDocumentStore()
    engine = PipelineCycleEngine(
        config={"analyst": {"min_fit_score": 70}},
        agents={"analyst": analyst_mock},
        doc_store=doc_store,
    )

    ok = engine.process_new_jobs(session)
    assert ok is True

    session.refresh(job)
    assert job.state == JobState.ANALYZED
    assert job.fit_score == 85


def test_engine_tailor_stage_success(session):
    job = Job(
        id="job2",
        title="Backend Dev",
        company="CloudCo",
        url="http://test.com",
        location="Remote",
        posted_date="today",
        jd_text="FastAPI backend",
        state=JobState.ANALYZED,
    )
    session.add(job)
    session.commit()

    tailor_mock = MagicMock()
    tailor_mock.run.return_value = {"basics": {"name": "Test Candidate"}, "work": []}

    doc_store = InMemoryDocumentStore()
    engine = PipelineCycleEngine(
        agents={"tailor": tailor_mock},
        doc_store=doc_store,
    )

    ok = engine.process_analyzed_jobs(session)
    assert ok is True

    session.refresh(job)
    assert job.state == JobState.DRAFTED
    assert doc_store.has_draft("job2")
    assert doc_store.load_draft("job2")["basics"]["name"] == "Test Candidate"


def test_engine_evidence_loop_unfixable(session):
    job = Job(
        id="job3",
        title="Principal Architect",
        company="MegaCorp",
        url="http://test.com",
        location="Remote",
        posted_date="today",
        jd_text="Needs 20 years Quantum experience",
        state=JobState.DRAFTED,
    )
    session.add(job)
    session.commit()

    critic_mock = MagicMock()
    critic_mock.run.return_value = MagicMock(unfixable=True, requirements=[])
    writer_mock = MagicMock()

    doc_store = InMemoryDocumentStore()
    notifications = []
    engine = PipelineCycleEngine(
        agents={"critic": critic_mock, "writer": writer_mock},
        doc_store=doc_store,
        notify_fn=lambda title, msg: notifications.append((title, msg)),
    )

    ok = engine.process_evidence_loop(session)
    assert ok is True

    session.refresh(job)
    assert job.state == JobState.UNFIXABLE
    assert len(notifications) == 1
    assert "UNFIXABLE" in notifications[0][1]


def test_engine_evidence_loop_needs_evidence_parking(session):
    job = Job(
        id="job4",
        title="ML Engineer",
        company="AI Lab",
        url="http://test.com",
        location="Remote",
        posted_date="today",
        jd_text="Kubernetes experience needed",
        state=JobState.DRAFTED,
    )
    session.add(job)
    session.commit()

    req_mock = MagicMock(requirement="Kubernetes", must_have=True, route="grill")
    critic_mock = MagicMock()
    critic_mock.run.return_value = MagicMock(unfixable=False, requirements=[req_mock])
    writer_mock = MagicMock()

    doc_store = InMemoryDocumentStore()
    notifications = []
    engine = PipelineCycleEngine(
        agents={"critic": critic_mock, "writer": writer_mock},
        doc_store=doc_store,
        notify_fn=lambda title, msg: notifications.append((title, msg)),
    )

    ok = engine.process_evidence_loop(session)
    assert ok is True

    session.refresh(job)
    assert job.state == JobState.NEEDS_EVIDENCE
    assert "Kubernetes" in job.grilling_transcript["gaps"]
    assert len(notifications) == 1
    assert "needs evidence: Kubernetes" in notifications[0][1]


def test_engine_retry_dlq_transition(session):
    job = Job(
        id="job5",
        title="DevOps",
        company="InfraCo",
        url="http://test.com",
        location="Remote",
        posted_date="today",
        jd_text="Terraform",
        state=JobState.NEW,
    )
    session.add(job)
    session.commit()

    analyst_mock = MagicMock()
    analyst_mock.run.side_effect = Exception("API Timeout")

    doc_store = InMemoryDocumentStore()
    engine = PipelineCycleEngine(
        agents={"analyst": analyst_mock},
        doc_store=doc_store,
    )

    # 1st failure: transient retry
    engine.process_new_jobs(session)
    session.refresh(job)
    assert job.state == JobState.NEW

    # 2nd failure
    engine.process_new_jobs(session)
    session.refresh(job)
    assert job.state == JobState.NEW

    # 3rd failure: moved to DLQ (FAILED)
    engine.process_new_jobs(session)
    session.refresh(job)
    assert job.state == JobState.FAILED
