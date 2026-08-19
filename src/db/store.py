import hashlib
from datetime import datetime
from typing import Optional

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


def build_manual_job(
    *,
    title: str = "",
    company: str = "",
    url: str = "",
    jd_text: str = "",
    notes: str = "",
    cv_path: Optional[str] = None,
    state: Optional["JobState"] = None,
    date_applied: Optional[str] = None,
) -> "Job":
    """Construct a Job row for a manual application.

    At least one identifying field (title/company/url) is required; the
    id is a uniqueness key, not a dedup key (see generate_manual_job_id).
    Defaults: source=manual, state=APPLIED, date_applied=today. The caller
    owns persistence (save_job) and the cv copy
    (DocumentStore.store_manual_cv).
    """
    from src.db.models import SOURCE_MANUAL, Job, JobState

    if not title and not company and not url:
        raise ValueError("Provide at least one of title, company, url.")

    if state is None:
        state = JobState.APPLIED
    return Job(
        id=generate_manual_job_id(url=url, title=title, company=company),
        url=url,
        title=title,
        company=company,
        location="",
        posted_date="",
        jd_text=jd_text,
        state=state,
        date_applied=date_applied or datetime.now().strftime("%Y-%m-%d"),
        cv_path=cv_path,
        source=SOURCE_MANUAL,
        notes=notes,
    )


def create_manual_job(
    engine,
    *,
    title: str = "",
    company: str = "",
    url: str = "",
    jd_text: str = "",
    notes: str = "",
    cv: Optional[str] = None,
    state: Optional["JobState"] = None,
    date_applied: Optional[str] = None,
) -> tuple[str, Optional[str], bool]:
    """Build, copy the CV into the resume store, and persist a manual
    application in one call.

    Returns (job_id, copied_cv, saved): job_id is the generated id
    (uniqueness key, not a dedup key); copied_cv is the path the CV was
    copied to (None when no CV was given); saved is False when a row with
    that id already exists — the copied CV is rolled back in that case.
    Raises ValueError for missing identifying fields or a CV path that
    does not exist.
    """
    import os

    from src.storage.document_store import DiskDocumentStore

    job = build_manual_job(
        title=title,
        company=company,
        url=url,
        jd_text=jd_text,
        notes=notes,
        state=state,
        date_applied=date_applied,
    )
    job_id = job.id

    copied_cv = None
    if cv:
        if not os.path.isfile(cv):
            raise ValueError(f"CV file not found: {cv}")
        copied_cv = DiskDocumentStore().store_manual_cv(job_id, cv)
        job.cv_path = copied_cv

    if not save_job(engine, job):
        if copied_cv:
            os.remove(copied_cv)
        return job_id, None, False
    return job_id, copied_cv, True


def pipeline_only(statement):
    """Restrict a job-selecting statement to pipeline applications."""
    from src.db.models import SOURCE_MANUAL, Job

    return statement.where(Job.source != SOURCE_MANUAL)


def is_manual_application(job) -> bool:
    """True when the row is a manual application (never pipeline work)."""
    from src.db.models import SOURCE_MANUAL

    return getattr(job, "source", None) == SOURCE_MANUAL


def find_jobs_by_url(engine, url: str) -> list:
    """Return existing rows sharing a url (empty when url is blank)."""
    from sqlmodel import select

    if not url:
        return []
    from src.db.models import Job

    with get_session(engine) as session:
        statement = select(Job).where(Job.url == url)
        return list(session.exec(statement).all())

