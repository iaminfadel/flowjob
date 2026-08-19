import pytest
from sqlmodel import create_engine, Session, SQLModel
from src.db.models import Job, JobState
from src.db.store import init_db, generate_manual_job_id

def test_schema_creates_correctly(tmp_path):
    db_path = tmp_path / "test.db"
    engine = init_db(str(db_path))
    
    # Check that tables exist
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "job" in tables
    assert "applicationrecord" not in tables

def test_columns_read_writable(tmp_path):
    db_path = tmp_path / "test.db"
    engine = init_db(str(db_path))
    
    job = Job(
        id="123",
        url="http://example.com",
        title="Software Engineer",
        company="Example Inc",
        location="Remote",
        posted_date="2023-01-01",
        jd_text="Great job",
        date_applied="2023-01-02",
        cv_path="/path/to/cv.pdf",
        fit_score=95,
        edit_score=85
    )
    
    with Session(engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)
        
        assert job.id == "123"
        assert job.date_applied == "2023-01-02"
        assert job.cv_path == "/path/to/cv.pdf"
        assert job.fit_score == 95
        assert job.edit_score == 85

def test_job_state_enum():
    assert JobState.NEEDS_EVIDENCE == "NEEDS_EVIDENCE"
    assert JobState.UNFIXABLE == "UNFIXABLE"

def test_job_grilling_transcript(tmp_path):
    db_path = tmp_path / "test.db"
    engine = init_db(str(db_path))
    
    job = Job(
        id="124",
        url="http://example.com/2",
        title="Software Engineer 2",
        company="Example Inc 2",
        location="Remote",
        posted_date="2023-01-01",
        jd_text="Great job 2",
        grilling_transcript={"active_requirement": "K8s", "gaps": {}}
    )
    
    with Session(engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)
        
        assert job.grilling_transcript == {"active_requirement": "K8s", "gaps": {}}

def test_new_schema_has_source_and_notes(tmp_path):
    db_path = tmp_path / "test.db"
    engine = init_db(str(db_path))

    with Session(engine) as session:
        job = Job(
            id="m1",
            url="",
            title="Manual Title",
            company="",
            location="",
            posted_date="",
            jd_text="",
            state=JobState.APPLIED,
            source="manual",
            notes="referred by a friend",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        assert job.source == "manual"
        assert job.notes == "referred by a friend"

def test_manual_row_requires_only_title(tmp_path):
    db_path = tmp_path / "test.db"
    engine = init_db(str(db_path))

    job = Job(
        id="m2",
        url="",
        title="Only A Title",
        company="",
        location="",
        posted_date="",
        jd_text="",
        state=JobState.APPLIED,
        source="manual",
    )

    with Session(engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)

        assert job.title == "Only A Title"
        assert job.source == "manual"
        assert job.state == JobState.APPLIED
        assert job.notes == ""

def test_migration_adds_source_and_notes_to_old_db(tmp_path):
    db_path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE job ("
            "id VARCHAR PRIMARY KEY, url VARCHAR NOT NULL, title VARCHAR NOT NULL,"
            "company VARCHAR NOT NULL, location VARCHAR NOT NULL, posted_date VARCHAR NOT NULL,"
            "jd_text VARCHAR NOT NULL, state VARCHAR NOT NULL,"
            "tailor_metadata JSON NOT NULL, grilling_transcript JSON NOT NULL,"
            "date_applied VARCHAR, cv_path VARCHAR, fit_score INTEGER, edit_score INTEGER)"
        )
        conn.exec_driver_sql(
            "INSERT INTO job (id, url, title, company, location, posted_date, jd_text, state,"
            " tailor_metadata, grilling_transcript, date_applied, cv_path)"
            " VALUES ('old1', 'u', 't', 'c', 'l', 'd', 'j', 'APPLIED', '{}', '{}', '2023-01-02', '/cv.pdf')"
        )
    engine.dispose()

    migrated = init_db(str(db_path))
    with Session(migrated) as session:
        job = session.get(Job, "old1")
        assert job is not None
        assert job.source == "pipeline"
        assert job.notes == ""
        assert job.date_applied == "2023-01-02"
        assert job.cv_path == "/cv.pdf"

def test_manual_job_id_unique_for_identical_fields():
    a = generate_manual_job_id(url="http://x", title="SWE", company="ACME")
    b = generate_manual_job_id(url="http://x", title="SWE", company="ACME")
    assert len(a) == 12
    assert a != b


def test_manual_job_id_hashes_only_provided_fields():
    title_only = generate_manual_job_id(title="SWE")
    with_company = generate_manual_job_id(title="SWE", company="ACME")
    full = generate_manual_job_id(url="http://x", title="SWE", company="ACME")
    assert title_only != with_company != full


def test_source_check_constraint_rejects_unknown_values(tmp_path):
    from sqlalchemy.exc import IntegrityError

    db_path = tmp_path / "test.db"
    engine = init_db(str(db_path))

    with Session(engine) as session:
        session.add(
            Job(
                id="bad",
                url="",
                title="Bad",
                company="",
                location="",
                posted_date="",
                jd_text="",
                source="manula",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

