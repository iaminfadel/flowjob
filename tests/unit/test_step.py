import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from src.db.models import Job, JobState, ErrorRecord
from src.pipeline.step import PipelineStep
from src.agents.runner import AgentRunner
from datetime import datetime

class FakeAgent(AgentRunner):
    def __init__(self, should_fail=False, fail_type="Exception", error_msg="fail"):
        super().__init__(None)
        self.should_fail = should_fail
        self.fail_type = fail_type
        self.error_msg = error_msg
        self.call_count = 0

    def run(self, job: Job):
        self.call_count += 1
        if self.should_fail:
            if self.fail_type == "RuntimeError":
                raise RuntimeError(self.error_msg)
            raise Exception(self.error_msg)

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_pipeline_step_success(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test", state=JobState.NEW)
    session.add(job)
    session.commit()

    agent = FakeAgent()
    step = PipelineStep(
        source_state=JobState.NEW,
        agent=agent,
        success_state=JobState.ANALYZED,
        fail_state=JobState.FAILED,
        agent_name="FakeAgent"
    )

    step.process(session)

    session.refresh(job)
    assert job.state == JobState.ANALYZED
    assert agent.call_count == 1

def test_pipeline_step_error_retry(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test", state=JobState.NEW)
    session.add(job)
    session.commit()

    agent = FakeAgent(should_fail=True)
    step = PipelineStep(
        source_state=JobState.NEW,
        agent=agent,
        success_state=JobState.ANALYZED,
        fail_state=JobState.SKIPPED,
        agent_name="FakeAgent"
    )

    # Retry 1
    step.process(session)
    session.refresh(job)
    assert job.state == JobState.SKIPPED
    
    # Check error record
    errors = session.exec(select(ErrorRecord)).all()
    assert len(errors) == 1
    assert errors[0].retry_count == 1

def test_pipeline_step_max_retries(session):
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test", state=JobState.NEW)
    session.add(job)
    
    # Pre-seed 2 retries
    err = ErrorRecord(job_id="1", agent_name="FakeAgent", error_type="Exception", stack_trace="", timestamp=datetime.now().isoformat(), retry_count=2)
    session.add(err)
    session.commit()

    agent = FakeAgent(should_fail=True)
    step = PipelineStep(
        source_state=JobState.NEW,
        agent=agent,
        success_state=JobState.ANALYZED,
        fail_state=JobState.SKIPPED,
        agent_name="FakeAgent"
    )

    # Retry 3 (fails permanently)
    step.process(session)
    session.refresh(job)
    assert job.state == JobState.FAILED

def test_pipeline_step_captcha_halt(session):
    job1 = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test", state=JobState.NEW)
    job2 = Job(id="2", title="SE2", company="Co", url="http", location="Remote", posted_date="today", jd_text="test", state=JobState.NEW)
    session.add(job1)
    session.add(job2)
    session.commit()

    agent = FakeAgent(should_fail=True, fail_type="RuntimeError", error_msg="CAPTCHA_DETECTED")
    step = PipelineStep(
        source_state=JobState.NEW,
        agent=agent,
        success_state=JobState.ANALYZED,
        fail_state=JobState.SKIPPED,
        agent_name="FakeAgent"
    )

    step.process(session)
    session.refresh(job1)
    session.refresh(job2)
    
    # One job fails permanently with CAPTCHA
    assert job1.state == JobState.FAILED
    
    # Loop should halt, so job2 remains NEW (if job1 was processed first, but DB order may vary)
    # Actually, as long as one is FAILED and one is NEW, it halted.
    states = [job1.state, job2.state]
    assert JobState.FAILED in states
    assert JobState.NEW in states
