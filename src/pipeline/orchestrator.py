import yaml
import traceback
from sqlmodel import select
from src.db.store import init_db, get_session
from src.db.models import JobPosting, JobState, ErrorRecord
from src.agents.analyst import AnalystAgent
from src.agents.tailor import TailorAgent
from src.agents.editor import EditorAgent
from src.agents.runner import AgentRunner
from datetime import datetime
import os
import yaml
import traceback

def log_job_error(session, agent_name: str, error: Exception, job_id: str):
    error_rec = ErrorRecord(
        agent_name=agent_name,
        error_type=type(error).__name__,
        stack_trace=traceback.format_exc(),
        job_id=job_id,
        timestamp=datetime.now().isoformat(),
        retry_count=0
    )
    session.add(error_rec)

def process_new_jobs(session, config):
    analyst_agent: AgentRunner = AnalystAgent()
    min_fit_score = config.get("analyst", {}).get("min_fit_score", 70)
    
    statement = select(JobPosting).where(JobPosting.state == JobState.NEW)
    new_jobs = session.exec(statement).all()
    
    print(f"Found {len(new_jobs)} NEW jobs.")
    
    for job in new_jobs:
        print(f"Analyzing job: {job.title} at {job.company}")
        try:
            fit_score = analyst_agent.run(job.jd_text)
            print(f"Fit score: {fit_score.score} - Recommendation: {fit_score.recommendation}")
            
            if fit_score.score >= min_fit_score:
                job.state = JobState.ANALYZED
                print(f"Job {job.id} passed fit threshold. State -> ANALYZED")
            else:
                job.state = JobState.SKIPPED
                print(f"Job {job.id} below fit threshold. State -> SKIPPED")
                
            session.add(job)
            session.commit()
        except Exception as e:
            print(f"Error analyzing job {job.id}: {e}")
            session.rollback()
            log_job_error(session, "AnalystAgent", e, job.id)
            session.commit()

def process_analyzed_jobs(session):
    tailor_agent: AgentRunner = TailorAgent()
    statement_analyzed = select(JobPosting).where(JobPosting.state == JobState.ANALYZED)
    analyzed_jobs = session.exec(statement_analyzed).all()
    
    print(f"Found {len(analyzed_jobs)} ANALYZED jobs.")
    
    for job in analyzed_jobs:
        print(f"Tailoring resume for job: {job.title} at {job.company}")
        try:
            output_dir = os.path.join("data", "resumes", job.id)
            feedback = job.tailor_metadata.get("feedback") if job.tailor_metadata else None
            pdf_path = tailor_agent.run(jd_text=job.jd_text, output_dir=output_dir, feedback=feedback)
            print(f"Generated tailored resume PDF: {pdf_path}")
            job.state = JobState.DRAFTED
            session.add(job)
            session.commit()
        except Exception as e:
            print(f"Error tailoring resume for job {job.id}: {e}")
            session.rollback()
            job.state = JobState.TAILOR_FAIL
            session.add(job)
            log_job_error(session, "TailorAgent", e, job.id)
            session.commit()

def process_drafted_jobs(session):
    editor_agent: AgentRunner = EditorAgent()
    statement = select(JobPosting).where(JobPosting.state == JobState.DRAFTED)
    drafted_jobs = session.exec(statement).all()
    
    print(f"Found {len(drafted_jobs)} DRAFTED jobs.")
    
    for job in drafted_jobs:
        print(f"Editing resume for job: {job.title} at {job.company}")
        try:
            pdf_path = os.path.join("data", "resumes", job.id, "resume.pdf")
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF not found at {pdf_path}")
                
            edit_score = editor_agent.run(jd_text=job.jd_text, pdf_path=pdf_path)
            print(f"Editor score: {edit_score.score} - Passed: {edit_score.passed}")
            
            if edit_score.passed:
                job.state = JobState.EDITED
                job.tailor_metadata = {}
                print(f"Job {job.id} passed Editor. State -> EDITED")
            else:
                retries = job.tailor_metadata.get("retries", 0) if job.tailor_metadata else 0
                if retries < 1:
                    print(f"Job {job.id} failed Editor. Retrying Tailor. Feedback: {edit_score.feedback}")
                    job.tailor_metadata = {"retries": retries + 1, "feedback": edit_score.feedback}
                    job.state = JobState.ANALYZED  # Send back to Tailor
                else:
                    print(f"Job {job.id} failed Editor. Max retries reached. State -> EDIT_FAIL")
                    job.state = JobState.EDIT_FAIL
                    
            session.add(job)
            session.commit()
        except Exception as e:
            print(f"Error editing resume for job {job.id}: {e}")
            session.rollback()
            log_job_error(session, "EditorAgent", e, job.id)
            session.commit()

def process_edited_jobs(session):
    statement = select(JobPosting).where(JobPosting.state == JobState.EDITED)
    edited_jobs = session.exec(statement).all()
    
    print(f"Found {len(edited_jobs)} EDITED jobs.")
    
    for job in edited_jobs:
        job.state = JobState.PENDING_APPROVAL
        print(f"Job {job.id} moved to PENDING_APPROVAL.")
        session.add(job)
    session.commit()

def run_pipeline(url: str = None, dry_run: bool = False):
    print(f"Pipeline started with url={url} and dry_run={dry_run}")
    
    with open("flowjob.yaml", "r") as f:
        config = yaml.safe_load(f)
        
    db_path = config.get("data", {}).get("db_path", "flowjob.db")
    engine = init_db(db_path)
    
    with get_session(engine) as session:
        process_new_jobs(session, config)
        process_analyzed_jobs(session)
        process_drafted_jobs(session)
        process_edited_jobs(session)
