import os
from datetime import datetime

import pytest
import yaml
from typer.testing import CliRunner

from src.cli import app
from src.db.store import init_db, get_session
from src.db.models import Job, JobState
from sqlmodel import select


def write_config(tmp_path, db_name="test.db"):
    db_path = tmp_path / db_name
    cfg = tmp_path / "flowjob.yaml"
    cfg.write_text(yaml.safe_dump({"data": {"db_path": str(db_path)}}))
    return str(cfg)


def load_jobs(cfg_path):
    with open(cfg_path) as f:
        db_path = yaml.safe_load(f)["data"]["db_path"]
    engine = init_db(db_path)
    with get_session(engine) as session:
        return session.exec(select(Job)).all()


@pytest.fixture()
def runner():
    return CliRunner()


def test_add_title_only_creates_manual_row_with_defaults(tmp_path, runner):
    cfg = write_config(tmp_path)
    expected_today = datetime.now().strftime("%Y-%m-%d")
    result = runner.invoke(app, ["add", "--config", cfg, "--title", "Only A Title"])

    assert result.exit_code == 0, result.output
    assert "source: manual" in result.output

    jobs = load_jobs(cfg)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Only A Title"
    assert job.company == ""
    assert job.url == ""
    assert job.source == "manual"
    assert job.state == JobState.APPLIED
    assert job.date_applied == expected_today
    assert job.notes == ""
    assert job.jd_text == ""
    assert job.cv_path is None


def test_add_full_flags_stores_jd_notes_and_copies_cv(tmp_path, runner):
    cfg = write_config(tmp_path)
    cv = tmp_path / "mycv.pdf"
    cv.write_bytes(b"fake-pdf")

    result = runner.invoke(app, [
        "add", "--config", cfg,
        "--title", "Data Engineer",
        "--company", "Rivendell",
        "--url", "https://rivendell.example/42",
        "--jd", "Build data pipelines in Rust.",
        "--notes", "referred by Gandalf",
        "--cv", str(cv),
        "--date-applied", "2026-07-01",
        "--state", "APPLIED",
    ])

    assert result.exit_code == 0, result.output
    assert "[source: manual]" in result.output or "source: manual" in result.output

    jobs = load_jobs(cfg)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.url == "https://rivendell.example/42"
    assert job.jd_text == "Build data pipelines in Rust."
    assert job.notes == "referred by Gandalf"
    assert job.date_applied == "2026-07-01"
    assert job.source == "manual"
    assert job.cv_path and job.cv_path.endswith("cv.pdf")
    assert os.path.exists(job.cv_path)
    assert job.cv_path.startswith(os.path.join("data", "resumes"))


def test_add_same_url_creates_separate_row_and_warns(tmp_path, runner):
    cfg = write_config(tmp_path)

    first = runner.invoke(app, [
        "add", "--config", cfg, "--title", "A", "--company", "ACME",
        "--url", "https://jobs.example.com/1",
    ])
    assert first.exit_code == 0, first.output
    first_id = first.output.split("[")[1].split("]")[0]

    second = runner.invoke(app, [
        "add", "--config", cfg, "--title", "A", "--company", "ACME",
        "--url", "https://jobs.example.com/1",
    ])
    assert second.exit_code == 0, second.output
    assert "already exists" in second.output
    assert first_id in second.output

    jobs = load_jobs(cfg)
    assert len(jobs) == 2
    assert {j.id for j in jobs} == {first_id, second.output.split("[")[1].split("]")[0]}
    assert all(j.url == "https://jobs.example.com/1" for j in jobs)


def test_add_requires_at_least_one_identifying_field(tmp_path, runner):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["add", "--config", cfg])
    assert result.exit_code == 1
    assert "at least one of" in result.output
    assert load_jobs(cfg) == []


def test_add_missing_cv_file_fails_without_saving(tmp_path, runner):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, [
        "add", "--config", cfg, "--title", "T", "--cv", "/nonexistent/cv.pdf",
    ])
    assert result.exit_code == 1
    assert "not found" in result.output
    assert load_jobs(cfg) == []


def test_add_invalid_state_rejected(tmp_path, runner):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, [
        "add", "--config", cfg, "--title", "T", "--state", "BOGUS",
    ])
    assert result.exit_code == 2
    assert load_jobs(cfg) == []


def test_build_manual_job_requires_an_identifying_field():
    from src.db.store import build_manual_job

    with pytest.raises(ValueError):
        build_manual_job()
    with pytest.raises(ValueError):
        build_manual_job(notes="only notes, no identity")


def test_update_flips_state_on_manual_row(tmp_path, runner):
    cfg = write_config(tmp_path)
    add = runner.invoke(app, ["add", "--config", cfg, "--title", "M", "--company", "ACME"])
    assert add.exit_code == 0
    job_id = add.output.split("[")[1].split("]")[0]

    result = runner.invoke(app, ["update", "--config", cfg, job_id, "--state", "REJECTED"])
    assert result.exit_code == 0, result.output
    assert "APPLIED → REJECTED" in result.output

    (job,) = load_jobs(cfg)
    assert job.state == JobState.REJECTED


def test_update_flips_state_on_pipeline_row(tmp_path, runner):
    cfg = write_config(tmp_path)
    with open(cfg) as f:
        db_path = yaml.safe_load(f)["data"]["db_path"]
    engine = init_db(db_path)
    from src.db.store import save_job
    from src.db.models import Job

    saved = save_job(engine, Job(
        id="pipeline1", url="u", title="Pipeline Job", company="C",
        location="", posted_date="", jd_text="", state=JobState.APPLIED,
        source="pipeline",
    ))
    assert saved

    result = runner.invoke(app, ["update", "--config", cfg, "pipeline1", "--state", "REJECTED"])
    assert result.exit_code == 0, result.output
    assert "APPLIED → REJECTED" in result.output
    assert "source: pipeline" in result.output

    (job,) = load_jobs(cfg)
    assert job.state == JobState.REJECTED


def test_update_unknown_id_exits_error(tmp_path, runner):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["update", "--config", cfg, "nope", "--state", "REJECTED"])
    assert result.exit_code == 1
    assert "No job with id" in result.output


def test_update_invalid_state_rejected(tmp_path, runner):
    cfg = write_config(tmp_path)
    result = runner.invoke(app, ["update", "--config", cfg, "x", "--state", "BOGUS"])
    assert result.exit_code == 2