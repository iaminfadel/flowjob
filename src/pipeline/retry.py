from sqlmodel import select
from src.db.models import Job, JobState, ErrorRecord

RETRY_STATE_BY_AGENT = {
    "AnalystAgent": JobState.NEW,
    "TailorAgent": JobState.ANALYZED,
    "EvidenceLoop": JobState.DRAFTED,
    "CoverageCritic": JobState.DRAFTED,
    "Writer": JobState.DRAFTED,
    "EditorAgent": JobState.DRAFTED,
    "ApplicatorAgent": JobState.PENDING_APPROVAL,
}


def requeue_failed_job(session, job: Job) -> JobState:
    """Re-queue a failed job at the stage its failing agent retries from.

    Resets the ErrorRecord retry_count so a DLQ'd job (retry_count >= 3) gets a
    fresh budget; the next pipeline cycle processes the job from its new state.
    Mirrors the pipeline's own retry mapping.
    """
    statement = select(ErrorRecord).where(ErrorRecord.job_id == job.id)
    err = session.exec(statement).first()

    if job.state == JobState.TAILOR_FAIL:
        target = JobState.ANALYZED
    elif job.state == JobState.EDIT_FAIL:
        target = JobState.DRAFTED
    else:
        target = RETRY_STATE_BY_AGENT.get(err.agent_name, JobState.NEW) if err else JobState.NEW

    job.state = target
    session.add(job)

    if err:
        err.retry_count = 0
        session.add(err)

    session.commit()
    return target