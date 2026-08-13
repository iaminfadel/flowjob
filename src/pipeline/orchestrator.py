import yaml
import traceback
from sqlmodel import select
from src.db.store import init_db, get_session
from src.db.models import JobPosting, JobState, ErrorRecord
from src.agents.analyst import AnalystAgent
from src.agents.runner import AgentRunner
from datetime import datetime

def run_pipeline(url: str = None, dry_run: bool = False):
    print(f"Pipeline started with url={url} and dry_run={dry_run}")
    
    with open("flowjob.yaml", "r") as f:
        config = yaml.safe_load(f)
        
    db_path = config.get("data", {}).get("db_path", "flowjob.db")
    engine = init_db(db_path)
    
    # 1. Initialize agents
    analyst_agent: AgentRunner = AnalystAgent()
    min_fit_score = config.get("analyst", {}).get("min_fit_score", 70)
    
    with get_session(engine) as session:
        # Fetch NEW jobs
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
                error_rec = ErrorRecord(
                    agent_name="AnalystAgent",
                    error_type=type(e).__name__,
                    stack_trace=traceback.format_exc(),
                    job_id=job.id,
                    timestamp=datetime.now().isoformat(),
                    retry_count=0
                )
                session.add(error_rec)
                session.commit()
