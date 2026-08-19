"""Unit tests for cockpit DB queries: source filtering, state flips, counts."""

import uuid

import pytest

from src.db.models import Job, JobState
from src.db.store import init_db, get_session
from src.tui import queries


@pytest.fixture
def seeded_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "cockpit.db"
    monkeypatch.setenv("FLOWJOB_DB", str(db_path))
    queries.reset_engine()
    engine = init_db(str(db_path))
    with get_session(engine) as session:
        session.add(
            Job(
                id="man1",
                url="https://example.com/man",
                title="Manual Role",
                company="ACME",
                location="",
                posted_date="",
                jd_text="pasted jd",
                state=JobState.APPLIED,
                source="manual",
                notes="referred by Alice",
                date_applied="2026-07-01",
            )
        )
        session.add(
            Job(
                id="pip1",
                url="https://example.com/pip",
                title="Pipeline Role",
                company="Globex",
                location="Remote",
                posted_date="2026-08-01",
                jd_text="scraped jd",
                state=JobState.APPLIED,
            )
        )
        session.add(
            Job(
                id="pip2",
                url="https://example.com/pip2",
                title="Rejected Role",
                company="Initech",
                location="",
                posted_date="",
                jd_text="",
                state=JobState.REJECTED,
            )
        )
        session.commit()
    return engine


def test_jobs_source_filter_manual(seeded_engine):
    rows = queries.jobs(source_filter="manual")
    assert [r["id"] for r in rows] == ["man1"]


def test_jobs_source_filter_pipeline(seeded_engine):
    rows = queries.jobs(source_filter="pipeline")
    assert {r["id"] for r in rows} == {"pip1", "pip2"}


def test_jobs_source_filter_all(seeded_engine):
    assert len(queries.jobs()) == 3
    assert len(queries.jobs(source_filter="ALL")) == 3


def test_jobs_combined_state_and_source_filters(seeded_engine):
    rows = queries.jobs(state_filter="APPLIED", source_filter="pipeline")
    assert [r["id"] for r in rows] == ["pip1"]
    assert queries.jobs(state_filter="APPLIED", source_filter="manual")[0]["id"] == "man1"


def test_jobs_carries_source_and_notes(seeded_engine):
    (row,) = queries.jobs(source_filter="manual")
    assert row["source"] == "manual"
    assert row["notes"] == "referred by Alice"
    assert row["date_applied"] == "2026-07-01"
    assert row["jd_text"] == "pasted jd"


def test_state_counts_count_manual_rows_as_applied(seeded_engine):
    """Watch-area cycle counts keep counting APPLIED regardless of source."""
    counts = queries.state_counts()
    assert counts["APPLIED"] == 2
    assert counts["REJECTED"] == 1


def test_set_job_state_flips_any_job(seeded_engine):
    assert queries.set_job_state("man1", "REJECTED") == "REJECTED"
    row = queries.job_detail("man1")
    assert row["state"] == "REJECTED"

    assert queries.set_job_state("pip1", "SKIPPED") == "SKIPPED"
    assert queries.job_detail("pip1")["state"] == "SKIPPED"


def test_set_job_state_unknown_id_returns_none(seeded_engine):
    assert queries.set_job_state("nope", "REJECTED") is None

def test_set_job_state_invalid_state_returns_none(seeded_engine):
    assert queries.set_job_state("man1", "BOGUS") is None
    assert queries.job_detail("man1")["state"] == "APPLIED"
