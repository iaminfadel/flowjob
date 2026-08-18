import pytest
from sqlmodel import Session, SQLModel, create_engine
from src.db.models import Job, JobState, ErrorRecord
from src.pipeline.retry import requeue_failed_job

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def add_error(session, job_id, agent_name, retry_count=3):
    session.add(ErrorRecord(agent_name=agent_name, error_type="RuntimeError", stack_trace="x", job_id=job_id, timestamp="2026-08-18T00:00:00", retry_count=retry_count))
    session.commit()

@pytest.mark.parametrize("agent_name,expected", [
    ("AnalystAgent", JobState.NEW),
    ("TailorAgent", JobState.ANALYZED),
    ("CoverageCritic", JobState.DRAFTED),
    ("Writer", JobState.DRAFTED),
    ("EditorAgent", JobState.DRAFTED),
    ("ApplicatorAgent", JobState.PENDING_APPROVAL),
    ("SomeUnknownAgent", JobState.NEW),
])
def test_requeue_mapping_by_agent(session, agent_name, expected):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="x", state=JobState.FAILED)
    session.add(job)
    add_error(session, "1", agent_name)

    result = requeue_failed_job(session, job)

    session.refresh(job)
    assert job.state == expected
    assert result == expected

def test_requeue_resets_retry_count(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="x", state=JobState.FAILED)
    session.add(job)
    add_error(session, "1", "ApplicatorAgent", retry_count=3)

    requeue_failed_job(session, job)

    err = session.exec(
        __import__("sqlmodel").select(ErrorRecord).where(ErrorRecord.job_id == "1")
    ).first()
    assert err.retry_count == 0

def test_requeue_handles_no_error_record(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="x", state=JobState.FAILED)
    session.add(job)
    session.commit()

    result = requeue_failed_job(session, job)

    session.refresh(job)
    assert job.state == JobState.NEW
    assert result == JobState.NEW

def test_requeue_handles_state_level_failures(session):
    for state, expected in [(JobState.TAILOR_FAIL, JobState.ANALYZED), (JobState.EDIT_FAIL, JobState.DRAFTED)]:
        job = Job(id=state.value, title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="x", state=state)
        session.add(job)
        session.commit()

        result = requeue_failed_job(session, job)

        session.refresh(job)
        assert job.state == expected
        assert result == expected
