from sqlmodel import select
from src.db.store import init_db, get_session
from src.db.models import JobPosting, JobState, ApplicationRecord
from src.agents.analyst import AnalystAgent
from datetime import datetime

def run_pipeline(url: str = None, dry_run: bool = False):
    print(f"Pipeline started with url={url} and dry_run={dry_run}")
    db_path = "flowjob.db" # Should be configurable
    engine = init_db(db_path)
    
    # 1. Initialize agents
    analyst_agent = AnalystAgent()
    min_fit_score = 70 # Default from config
    
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
                    
                    app_record = session.get(ApplicationRecord, job.id)
                    if not app_record:
                        app_record = ApplicationRecord(
                            id=job.id,
                            company=job.company,
                            role=job.title,
                            job_url=job.url,
                            state=JobState.ANALYZED,
                            date_first_seen=datetime.now().isoformat(),
                            fit_score=fit_score.score
                        )
                        session.add(app_record)
                else:
                    job.state = JobState.SKIPPED
                    print(f"Job {job.id} below fit threshold. State -> SKIPPED")
                    
                session.add(job)
                session.commit()
            except Exception as e:
                print(f"Error analyzing job {job.id}: {e}")
