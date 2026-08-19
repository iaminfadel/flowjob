"""The pipeline never processes manual applications.

Every job-selecting stage query excludes source=manual; a manual row is
never requeued, retried, or reprocessed even when its state looks
pipeline-like; CLI status counts and the evidence listing ignore manual
rows.
"""

import pytest
import yaml
from sqlmodel import Session, SQLModel, create_engine, select
from typer.testing import CliRunner
from unittest.mock import MagicMock

from src.cli import app
from src.db.models import ErrorRecord, FitScore, Job, JobState
from src.db.store import init_db, get_session
from src.pipeline.engine import PipelineCycleEngine
from src.pipeline.retry import requeue_failed_job
from src.pipeline.step import PipelineStep
from src.agents.runner import AgentRunner


def make_job(job_id, state, source="pipeline"):
    return Job(
        id=job_id,
        title=f"Role {job_id}",
        company="Co",
        url=f"https://example.com/{job_id}",
        location="Remote",
        posted_date="today",
        jd_text="jd",
        state=state,
        source=source,
    )


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


class FakeAgent(AgentRunner):
    def __init__(self):
        super().__init__(None)
        self.processed = []

    def run(self, job: Job):
        self.processed.append(job.id)
        job.state = JobState.ANALYZED


def test_pipeline_step_skips_manual_rows(session):
    session.add(make_job("manual1", JobState.NEW, source="manual"))
    session.add(make_job("pip1", JobState.NEW))
    session.commit()

    agent = FakeAgent()
    step = PipelineStep(
        source_state=JobState.NEW,
        agent=agent,
        success_state=JobState.ANALYZED,
        fail_state=JobState.FAILED,
        agent_name="FakeAgent",
    )

    step.process(session)

    session.refresh(session.get(Job, "manual1"))
    session.refresh(session.get(Job, "pip1"))
    assert session.get(Job, "manual1").state == JobState.NEW
    assert session.get(Job, "pip1").state == JobState.ANALYZED
    assert agent.processed == ["pip1"]


def test_engine_analyst_stage_skips_manual_rows(session):
    session.add(make_job("manual1", JobState.NEW, source="manual"))
    session.add(make_job("pip1", JobState.NEW))
    session.commit()

    analyst_mock = MagicMock()
    analyst_mock.run.return_value = FitScore(
        score=85, matching_skills=["Python"], missing_skills=[], recommendation="apply"
    )
    engine = PipelineCycleEngine(
        config={"analyst": {"min_fit_score": 70}},
        agents={"analyst": analyst_mock},
    )

    ok = engine.process_new_jobs(session)
    assert ok is True
    assert analyst_mock.run.call_count == 1
    assert session.get(Job, "manual1").state == JobState.NEW
    assert session.get(Job, "pip1").state == JobState.ANALYZED


def test_engine_edited_stage_skips_manual_rows(session):
    session.add(make_job("manual1", JobState.EDITED, source="manual"))
    session.add(make_job("pip1", JobState.EDITED))
    session.commit()

    engine = PipelineCycleEngine(agents={})
    engine.process_edited_jobs(session)

    assert session.get(Job, "manual1").state == JobState.EDITED
    assert session.get(Job, "pip1").state == JobState.PENDING_APPROVAL


def _seed_error(session, job_id, agent_name="ApplicatorAgent"):
    session.add(
        ErrorRecord(
            agent_name=agent_name,
            error_type="RuntimeError",
            stack_trace="x",
            job_id=job_id,
            timestamp="2026-08-19T00:00:00",
            retry_count=1,
        )
    )
    session.commit()


def test_engine_retries_skip_manual_rows(session):
    session.add(make_job("manual1", JobState.FAILED, source="manual"))
    session.add(make_job("pip1", JobState.FAILED))
    session.commit()
    _seed_error(session, "manual1")
    _seed_error(session, "pip1")

    engine = PipelineCycleEngine(agents={})
    engine.process_retries(session)

    assert session.get(Job, "manual1").state == JobState.FAILED
    assert session.get(Job, "pip1").state == JobState.PENDING_APPROVAL


def test_orchestrator_analyst_stage_skips_manual_rows(session):
    from src.pipeline.orchestrator import process_new_jobs

    session.add(make_job("manual1", JobState.NEW, source="manual"))
    session.add(make_job("pip1", JobState.NEW))
    session.commit()

    analyst_mock = MagicMock()
    analyst_mock.run.return_value = FitScore(
        score=85, matching_skills=["Python"], missing_skills=[], recommendation="apply"
    )

    process_new_jobs(session, {"analyst": {"min_fit_score": 70}}, analyst_mock)

    assert analyst_mock.run.call_count == 1
    assert session.get(Job, "manual1").state == JobState.NEW
    assert session.get(Job, "pip1").state == JobState.ANALYZED


def test_orchestrator_retries_skip_manual_rows(session):
    from src.pipeline.orchestrator import process_retries

    session.add(make_job("manual1", JobState.FAILED, source="manual"))
    session.add(make_job("pip1", JobState.FAILED))
    session.commit()
    _seed_error(session, "manual1")
    _seed_error(session, "pip1")

    process_retries(session)

    assert session.get(Job, "manual1").state == JobState.FAILED
    assert session.get(Job, "pip1").state == JobState.PENDING_APPROVAL


def test_requeue_failed_job_refuses_manual(session):
    job = make_job("manual1", JobState.FAILED, source="manual")
    session.add(job)
    _seed_error(session, "manual1")

    with pytest.raises(ValueError, match="manual"):
        requeue_failed_job(session, job)

    session.refresh(job)
    assert job.state == JobState.FAILED


def test_tui_requeue_job_returns_none_for_manual(tmp_path, monkeypatch):
    db_path = tmp_path / "cockpit.db"
    monkeypatch.setenv("FLOWJOB_DB", str(db_path))
    from src.tui import queries

    queries.reset_engine()
    engine = init_db(str(db_path))
    with get_session(engine) as session:
        session.add(make_job("manual1", JobState.FAILED, source="manual"))
        session.add(make_job("pip1", JobState.FAILED))
        session.commit()
        _seed_error(session, "manual1")
        _seed_error(session, "pip1")

    assert queries.requeue_job("manual1") is None
    assert queries.requeue_job("pip1") == JobState.PENDING_APPROVAL.value


def write_config(tmp_path, db_name="test.db"):
    db_path = tmp_path / db_name
    cfg = tmp_path / "flowjob.yaml"
    cfg.write_text(yaml.safe_dump({"data": {"db_path": str(db_path)}}))
    return str(cfg)


def test_cli_status_excludes_manual_counts(tmp_path):
    cfg = write_config(tmp_path)
    with open(cfg) as f:
        db_path = yaml.safe_load(f)["data"]["db_path"]
    engine = init_db(db_path)
    with get_session(engine) as session:
        session.add(make_job("manual1", JobState.APPLIED, source="manual"))
        session.add(make_job("manual2", JobState.NEW, source="manual"))
        session.add(make_job("pip1", JobState.APPLIED))
        session.add(make_job("pip2", JobState.NEW))
        session.commit()

    result = CliRunner().invoke(app, ["status", "--config", cfg])

    assert result.exit_code == 0, result.output
    assert "APPLIED: 1" in result.output
    assert "NEW: 1" in result.output


def test_cli_grill_listing_excludes_manual(tmp_path):
    cfg = write_config(tmp_path)
    with open(cfg) as f:
        db_path = yaml.safe_load(f)["data"]["db_path"]
    engine = init_db(db_path)
    with get_session(engine) as session:
        session.add(make_job("manual1", JobState.NEEDS_EVIDENCE, source="manual"))
        session.add(make_job("pip1", JobState.NEEDS_EVIDENCE))
        session.commit()

    result = CliRunner().invoke(app, ["grill", "--config", cfg])

    assert result.exit_code == 0, result.output
    assert "pip1" in result.output
    assert "manual1" not in result.output