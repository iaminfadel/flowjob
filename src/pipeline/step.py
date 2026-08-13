from typing import Optional, Callable
from sqlmodel import select, Session
from src.db.models import Job, JobState, ErrorRecord
from src.agents.runner import AgentRunner
import traceback
from datetime import datetime

class PipelineStep:
    def __init__(
        self,
        source_state: JobState,
        agent: AgentRunner,
        success_state: JobState,
        fail_state: JobState,
        agent_name: str,
        step_func: Optional[Callable] = None
    ):
        self.source_state = source_state
        self.agent = agent
        self.success_state = success_state
        self.fail_state = fail_state
        self.agent_name = agent_name
        self.step_func = step_func

    def _log_job_error(self, session: Session, error: Exception, job_id: str) -> int:
        statement = select(ErrorRecord).where(ErrorRecord.job_id == job_id)
        error_rec = session.exec(statement).first()
        
        if error_rec:
            error_rec.error_type = type(error).__name__
            error_rec.stack_trace = traceback.format_exc()
            error_rec.timestamp = datetime.now().isoformat()
            error_rec.retry_count += 1
            error_rec.agent_name = self.agent_name
        else:
            error_rec = ErrorRecord(
                agent_name=self.agent_name,
                error_type=type(error).__name__,
                stack_trace=traceback.format_exc(),
                job_id=job_id,
                timestamp=datetime.now().isoformat(),
                retry_count=1
            )
        session.add(error_rec)
        return error_rec.retry_count

    def _handle_job_failure(self, session: Session, error: Exception, job: Job, force_fail: bool = False):
        print(f"Error applying to job {job.id}: {error}")
        session.rollback()
        
        retry_count = self._log_job_error(session, error, job.id)
        
        if force_fail or retry_count >= 3:
            print(f"Job {job.id} failed 3 times (or forced). Moving to DLQ (FAILED).")
            job.state = JobState.FAILED
        else:
            print(f"Job {job.id} transient error ({retry_count}/3). Moving to {self.fail_state}.")
            job.state = self.fail_state
            
        session.add(job)
        session.commit()

    def process(self, session: Session):
        statement = select(Job).where(Job.state == self.source_state)
        jobs = session.exec(statement).all()
        
        for job in jobs:
            try:
                if self.step_func:
                    self.step_func(job, self.agent, self.success_state, self.fail_state)
                else:
                    self.agent.run(job)
                    job.state = self.success_state
                session.add(job)
                session.commit()
            except RuntimeError as e:
                if str(e) == "CAPTCHA_DETECTED":
                    print(f"CAPTCHA detected for job {job.id}. Halting pipeline immediately.")
                    self._handle_job_failure(session, e, job, force_fail=True)
                    break
                else:
                    self._handle_job_failure(session, e, job)
            except Exception as e:
                self._handle_job_failure(session, e, job)
