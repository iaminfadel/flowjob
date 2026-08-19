"""DB read helpers for the cockpit.

All queries run on short-lived sessions against a module-cached engine —
the pipeline writes from its own worker thread/session. Enables WAL.
"""

from __future__ import annotations

import os

from sqlmodel import select, func

from src.config import load_config
from src.db.store import init_db, get_session
from src.db.models import Job, JobState, LLMInteraction, PipelineRun, ErrorRecord

_engine = None


def engine():
    global _engine
    if _engine is None:
        cfg = load_config("flowjob.yaml")
        db_path = os.environ.get("FLOWJOB_DB") or cfg.data.db_path
        _engine = init_db(db_path)
    return _engine


def reset_engine() -> None:
    global _engine
    _engine = None


def with_session(fn):
    with get_session(engine()) as session:
        return fn(session)


def job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "url": job.url,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "posted_date": job.posted_date,
        "state": job.state.value if isinstance(job.state, JobState) else job.state,
        "fit_score": job.fit_score,
        "edit_score": job.edit_score,
        "cv_path": job.cv_path or "",
        "jd_text": job.jd_text,
        "grilling_transcript": job.grilling_transcript or {},
        "tailor_metadata": job.tailor_metadata or {},
        "date_applied": job.date_applied,
        "source": job.source,
        "notes": job.notes,
    }


def state_counts() -> dict[str, int]:
    def _count(session, state: JobState) -> int:
        stmt = select(func.count()).select_from(Job).where(Job.state == state)
        return session.exec(stmt).one()

    def _run(session):
        return {s.value: _count(session, s) for s in JobState}

    return with_session(_run)


def total_jobs() -> int:
    def _run(session):
        return session.exec(select(func.count(Job.id))).one()

    return with_session(_run)


def jobs(state_filter: str | None = None, source_filter: str | None = None) -> list[dict]:
    def _run(session):
        stmt = select(Job)
        if state_filter and state_filter != "ALL":
            stmt = stmt.where(Job.state == state_filter)
        if source_filter and source_filter != "ALL":
            stmt = stmt.where(Job.source == source_filter)
        stmt = stmt.order_by(Job.state, Job.company)
        return [job_to_dict(j) for j in session.exec(stmt).all()]

    return with_session(_run)


def job_detail(job_id: str) -> dict | None:
    def _run(session):
        job = session.get(Job, job_id)
        return job_to_dict(job) if job else None

    return with_session(_run)


def error_record(job_id: str) -> dict | None:
    def _run(session):
        stmt = select(ErrorRecord).where(ErrorRecord.job_id == job_id)
        err = session.exec(stmt).first()
        if not err:
            return None
        return {
            "agent_name": err.agent_name,
            "error_type": err.error_type,
            "stack_trace": err.stack_trace,
            "retry_count": err.retry_count,
            "timestamp": err.timestamp,
        }

    return with_session(_run)


def last_cycle() -> str | None:
    def _run(session):
        stmt = select(PipelineRun).order_by(PipelineRun.id.desc()).limit(1)
        run = session.exec(stmt).first()
        return run.timestamp if run else None

    return with_session(_run)


def spend_summary() -> dict:
    def _run(session):
        rows = session.exec(select(LLMInteraction)).all()
        return {
            "calls": len(rows),
            "cost_usd": sum(r.cost_usd for r in rows),
            "tokens": sum(r.prompt_tokens + r.completion_tokens for r in rows),
            "cached_tokens": sum(r.cached_tokens for r in rows),
            "failures": sum(1 for r in rows if not r.success),
        }

    return with_session(_run)


def llm_logs(limit: int = 200) -> list[dict]:
    def _run(session):
        stmt = select(LLMInteraction).order_by(LLMInteraction.id.desc()).limit(limit)
        return [
            {
                "timestamp": r.timestamp,
                "agent_name": r.agent_name,
                "job_id": r.job_id,
                "provider": r.provider,
                "model": r.model,
                "tokens": r.prompt_tokens + r.completion_tokens,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "success": r.success,
                "error": r.error,
            }
            for r in session.exec(stmt).all()
        ]

    return with_session(_run)


def grilling_gaps(job_id: str) -> dict:
    detail = job_detail(job_id)
    if not detail:
        return {}
    return detail["grilling_transcript"].get("gaps", {})


def requeue_job(job_id: str) -> str | None:
    """Re-queue a failed job (retry action); returns the target state or None.

    Manual applications are refused — they are never pipeline work, even when
    their state looks pipeline-like.
    """

    def _run(session):
        from src.pipeline.retry import requeue_failed_job

        job = session.get(Job, job_id)
        if not job:
            return None
        try:
            target = requeue_failed_job(session, job)
        except ValueError:
            return None
        return target.value

    return with_session(_run)


def set_job_state(job_id: str, state: str) -> str | None:
    """Flip any job's state (manual or pipeline); returns the new state or None."""

    def _run(session):
        job = session.get(Job, job_id)
        if not job:
            return None
        try:
            job.state = JobState(state)
        except ValueError:
            return None
        session.commit()
        return job.state.value

    return with_session(_run)
