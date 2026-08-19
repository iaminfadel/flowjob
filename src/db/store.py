import hashlib
from datetime import datetime

from sqlmodel import SQLModel, create_engine, Session


def _migrate_schema(conn) -> None:
    """Add columns introduced after the original schema, without data loss.

    `create_all` never alters existing tables, so columns added to the
    Job model must be applied to live databases via ALTER TABLE.
    """
    from sqlalchemy import inspect

    cols = {c["name"] for c in inspect(conn).get_columns("job")}
    if "source" not in cols:
        conn.exec_driver_sql(
            "ALTER TABLE job ADD COLUMN source VARCHAR NOT NULL DEFAULT 'pipeline' "
            "CHECK (source IN ('manual', 'pipeline'))"
        )
    if "notes" not in cols:
        conn.exec_driver_sql("ALTER TABLE job ADD COLUMN notes VARCHAR NOT NULL DEFAULT ''")


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

    # Bring existing databases up to the current schema
    with engine.connect() as conn:
        _migrate_schema(conn)
    
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


def generate_manual_job_id(url: str = "", title: str = "", company: str = "") -> str:
    """Key for a manual application row.

    Hashes the identifying fields actually provided — in the same
    concatenation order as the pipeline id (`url + title + company`,
    see scout.generate_id) — plus a microsecond timestamp, so two
    entries with identical fields never collide. Deliberately NOT
    idempotent: the decided collision policy for manual applications
    is a separate row with a warning, never a merge (charting round,
    recorded in the wayfinder map's out-of-scope section).
    """
    raw = f"{url}{title}{company}{datetime.now().isoformat()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]

