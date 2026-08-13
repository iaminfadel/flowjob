from sqlmodel import create_engine, Session, SQLModel
from src.db.models import Job, JobState
from src.db.store import init_db

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
