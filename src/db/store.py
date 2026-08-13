from sqlmodel import SQLModel, create_engine, Session

def init_db(db_path: str):
    """Initialize the SQLite database with the required schema."""
    sqlite_url = f"sqlite:///{db_path}"
    engine = create_engine(sqlite_url)
    
    # Create all tables
    import src.db.models  # Ensure models are registered
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    
    return engine

def get_session(engine) -> Session:
    """Return a database session."""
    return Session(engine)

def save_job(engine, job: "Job") -> bool:
    """
    Save a Job to the database if it doesn't already exist.
    Returns True if the job was newly saved, False if it was a duplicate.
    """
    from src.db.models import Job
    with get_session(engine) as session:
        existing_job = session.get(Job, job.id)
        if existing_job:
            return False
        session.add(job)
        session.commit()
        return True

