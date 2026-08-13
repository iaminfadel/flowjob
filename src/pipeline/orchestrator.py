import yaml
import traceback
from sqlmodel import select
from src.db.store import init_db, get_session
from src.db.models import Job, JobState, ErrorRecord
from src.agents.analyst import AnalystAgent
from src.agents.tailor import TailorAgent
from src.agents.editor import EditorAgent
from src.agents.applicator import ApplicatorAgent
from src.agents.runner import AgentRunner
from datetime import datetime
import os
import subprocess

def log_job_error(session, agent_name: str, error: Exception, job_id: str) -> int:
    statement = select(ErrorRecord).where(ErrorRecord.job_id == job_id)
    error_rec = session.exec(statement).first()
    
    if error_rec:
        error_rec.error_type = type(error).__name__
        error_rec.stack_trace = traceback.format_exc()
        error_rec.timestamp = datetime.now().isoformat()
        error_rec.retry_count += 1
        error_rec.agent_name = agent_name
    else:
        error_rec = ErrorRecord(
            agent_name=agent_name,
            error_type=type(error).__name__,
            stack_trace=traceback.format_exc(),
            job_id=job_id,
            timestamp=datetime.now().isoformat(),
            retry_count=1
        )
    session.add(error_rec)
    return error_rec.retry_count

def handle_job_failure(session, agent_name: str, error: Exception, job, fallback_state=JobState.FAILED, force_fail=False):
    print(f"Error applying to job {job.id}: {error}")
    session.rollback()
    
    retry_count = log_job_error(session, agent_name, error, job.id)
    
    if force_fail or retry_count >= 3:
        print(f"Job {job.id} failed 3 times (or forced). Moving to DLQ (FAILED).")
        job.state = JobState.FAILED
    else:
        print(f"Job {job.id} transient error ({retry_count}/3). Moving to {fallback_state}.")
        job.state = fallback_state
        
    session.add(job)
    session.commit()

def run_agent_step(session, agent_name: str, job, fallback_state: JobState, step_func):
    try:
        step_func(job)
        session.add(job)
        session.commit()
        return True
    except RuntimeError as e:
        if str(e) == "CAPTCHA_DETECTED":
            print(f"CAPTCHA detected for job {job.id}. Halting pipeline immediately.")
            handle_job_failure(session, agent_name, e, job, fallback_state, force_fail=True)
            return False
        else:
            handle_job_failure(session, agent_name, e, job, fallback_state)
            return True
    except Exception as e:
        handle_job_failure(session, agent_name, e, job, fallback_state)
        return True

def prompt_user_approval(job) -> bool:
    print(f"Prompting user for job: {job.title} at {job.company}")
    try:
        subprocess.run(["notify-send", "FlowJob: Job ready for approval!", f"{job.title} at {job.company}"])
    except FileNotFoundError:
        print("notify-send not found, skipping OS notification.")
        
    choice = input(f"Apply to {job.title} at {job.company}? [y/N]: ")
    return choice.strip().lower() == 'y'

def process_retries(session):
    statement = select(ErrorRecord).where(ErrorRecord.retry_count > 0).where(ErrorRecord.retry_count < 3)
    errors = session.exec(statement).all()
    
    count = 0
    for err in errors:
        job = session.get(Job, err.job_id)
        if not job:
            continue
            
        if job.state == JobState.TAILOR_FAIL:
            job.state = JobState.ANALYZED
            count += 1
        elif job.state == JobState.EDIT_FAIL:
            job.state = JobState.DRAFTED
            count += 1
        elif job.state == JobState.FAILED and err.agent_name == "ApplicatorAgent":
            job.state = JobState.PENDING_APPROVAL
            count += 1
            
        if count > 0:
            session.add(job)
            
    if count > 0:
        session.commit()
        print(f"Retrying {count} transient errors...")

def process_new_jobs(session, config):
    analyst_agent: AgentRunner = AnalystAgent()
    min_fit_score = config.get("analyst", {}).get("min_fit_score", 70)
    
    statement = select(Job).where(Job.state == JobState.NEW)
    new_jobs = session.exec(statement).all()
    
    print(f"Found {len(new_jobs)} NEW jobs.")
    
    for job in new_jobs:
        print(f"Analyzing job: {job.title} at {job.company}")
        def _step(j):
            fit_score = analyst_agent.run({"jd_text": j.jd_text})
            print(f"Fit score: {fit_score.score} - Recommendation: {fit_score.recommendation}")
            if fit_score.score >= min_fit_score:
                j.state = JobState.ANALYZED
                print(f"Job {j.id} passed fit threshold. State -> ANALYZED")
            else:
                j.state = JobState.SKIPPED
                print(f"Job {j.id} below fit threshold. State -> SKIPPED")
        if not run_agent_step(session, "AnalystAgent", job, JobState.NEW, _step):
            break

def process_analyzed_jobs(session):
    tailor_agent: AgentRunner = TailorAgent()
    statement = select(Job).where(Job.state == JobState.ANALYZED)
    analyzed_jobs = session.exec(statement).all()
    
    print(f"Found {len(analyzed_jobs)} ANALYZED jobs.")
    
    for job in analyzed_jobs:
        print(f"Tailoring resume for job: {job.title} at {job.company}")
        def _step(j):
            output_dir = os.path.join("data", "resumes", j.id)
            feedback = j.tailor_metadata.get("feedback") if j.tailor_metadata else None
            pdf_path = tailor_agent.run(jd_text=j.jd_text, output_dir=output_dir, feedback=feedback)
            print(f"Generated tailored resume PDF: {pdf_path}")
            j.state = JobState.DRAFTED
        if not run_agent_step(session, "TailorAgent", job, JobState.TAILOR_FAIL, _step):
            break

def process_drafted_jobs(session):
    editor_agent: AgentRunner = EditorAgent()
    statement = select(Job).where(Job.state == JobState.DRAFTED)
    drafted_jobs = session.exec(statement).all()
    
    print(f"Found {len(drafted_jobs)} DRAFTED jobs.")
    
    for job in drafted_jobs:
        print(f"Editing resume for job: {job.title} at {job.company}")
        def _step(j):
            pdf_path = os.path.join("data", "resumes", j.id, "resume.pdf")
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF not found at {pdf_path}")
                
            edit_score = editor_agent.run({"jd_text": j.jd_text, "pdf_path": pdf_path})
            print(f"Editor score: {edit_score.score} - Passed: {edit_score.passed}")
            
            if edit_score.passed:
                j.state = JobState.EDITED
                j.tailor_metadata = {}
                print(f"Job {j.id} passed Editor. State -> EDITED")
            else:
                retries = j.tailor_metadata.get("retries", 0) if j.tailor_metadata else 0
                if retries < 1:
                    print(f"Job {j.id} failed Editor. Retrying Tailor. Feedback: {edit_score.feedback}")
                    j.tailor_metadata = {"retries": retries + 1, "feedback": edit_score.feedback}
                    j.state = JobState.ANALYZED
                else:
                    print(f"Job {j.id} failed Editor. Max retries reached. State -> EDIT_FAIL")
                    j.state = JobState.EDIT_FAIL
        if not run_agent_step(session, "EditorAgent", job, JobState.DRAFTED, _step):
            break

def process_edited_jobs(session):
    statement = select(Job).where(Job.state == JobState.EDITED)
    edited_jobs = session.exec(statement).all()
    
    print(f"Found {len(edited_jobs)} EDITED jobs.")
    
    for job in edited_jobs:
        job.state = JobState.PENDING_APPROVAL
        print(f"Job {job.id} moved to PENDING_APPROVAL.")
        session.add(job)
    session.commit()

def process_pending_approval_jobs(session):
    statement = select(Job).where(Job.state == JobState.PENDING_APPROVAL)
    pending_jobs = session.exec(statement).all()
    
    if pending_jobs:
        print(f"Found {len(pending_jobs)} PENDING_APPROVAL jobs.")
        applicator_agent: AgentRunner = ApplicatorAgent()
        
    for job in pending_jobs:
        def _step(j):
            if prompt_user_approval(j):
                success = applicator_agent.run(j)
                if success:
                    j.state = JobState.APPLIED
                    print(f"Job {j.id} successfully APPLIED.")
                else:
                    j.state = JobState.FAILED
                    print(f"Job {j.id} application FAILED.")
            else:
                print(f"Job {j.id} skipped by user.")
                j.state = JobState.SKIPPED
        if not run_agent_step(session, "ApplicatorAgent", job, JobState.FAILED, _step):
            break

def run_pipeline(url: str = None, dry_run: bool = False):
    print(f"Pipeline started with url={url} and dry_run={dry_run}")
    
    from src.tools.browser import check_session_health
    if not check_session_health():
        import sys
        sys.exit(1)

    with open("flowjob.yaml", "r") as f:
        config = yaml.safe_load(f)
        
    db_path = config.get("data", {}).get("db_path", "flowjob.db")
    engine = init_db(db_path)
    
    with get_session(engine) as session:
        process_retries(session)
        process_new_jobs(session, config)
        process_analyzed_jobs(session)
        process_drafted_jobs(session)
        process_edited_jobs(session)
        process_pending_approval_jobs(session)

        if not dry_run:
            from src.db.models import PipelineRun
            run_record = PipelineRun(timestamp=datetime.now().isoformat(), success=True)
            session.add(run_record)
            session.commit()
