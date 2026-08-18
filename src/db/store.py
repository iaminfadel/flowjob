from sqlmodel import SQLModel, create_engine, Session

def init_db(db_path: str):
    """Initialize the SQLite database with the required schema.

    Creates missing tables only — never drops existing data.
    Enables WAL journal mode and a busy timeout so concurrent readers
    (e.g. the TUI) do not hit 'database is locked' while the pipeline writes.
    """
    sqlite_url = f"sqlite:///{db_path}"
    engine = create_engine(sqlite_url)

    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA busy_timeout=5000")

    # Create all tables (idempotent; preserves existing rows)
    import src.db.models  # Ensure models are registered
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

