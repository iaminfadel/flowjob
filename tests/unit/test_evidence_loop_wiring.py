import pytest
from unittest.mock import MagicMock, patch
from sqlmodel import create_engine, Session, SQLModel
from src.db.models import Job, JobState
from src.agents.coverage_critic import CoverageReport, RequirementCheck
from src.pipeline.orchestrator import process_evidence_loop, save_draft_json, load_draft_json

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def setup_drafted_job(session, job_id="job_ev_1", jd_text="Must know Go and Kubernetes"):
    job = Job(
        id=job_id,
        url="http://example.com",
        title="Senior Go Engineer",
        company="GoCorp",
        location="Remote",
        posted_date="2023-01-01",
        jd_text=jd_text,
        state=JobState.DRAFTED,
        cv_path=None
    )
    session.add(job)
    session.commit()
    save_draft_json(job_id, {"work": [{"company": "Tech Corp", "highlights": ["Built Go services"]}]})
    return job

def test_evidence_loop_unfixable(session):
    job = setup_job = setup_drafted_job(session, "job_unfixable")
    
    mock_critic = MagicMock()
    mock_critic.run.return_value = CoverageReport(
        unfixable=True,
        requirements=[RequirementCheck(requirement="Security Clearance", must_have=True, verdict="missing", route="drop")],
        summary="Candidate lacks clearance."
    )
    mock_writer = MagicMock()

    process_evidence_loop(session, mock_critic, mock_writer)

    session.refresh(job)
    assert job.state == JobState.UNFIXABLE

def test_evidence_loop_grill_route(session):
    job = setup_drafted_job(session, "job_grill")
    
    mock_critic = MagicMock()
    mock_critic.run.return_value = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="Kubernetes production experience",
                must_have=True,
                verdict="missing",
                route="grill",
                support=[]
            )
        ],
        summary="Need grilling on K8s"
    )
    mock_writer = MagicMock()

    process_evidence_loop(session, mock_critic, mock_writer)

    session.refresh(job)
    assert job.state == JobState.NEEDS_EVIDENCE
    assert job.grilling_transcript["active_requirement"] == "Kubernetes production experience"
    assert "Kubernetes production experience" in job.grilling_transcript["gaps"]

def test_evidence_loop_fix_and_converge(session):
    job = setup_drafted_job(session, "job_fix_converge")

    # Round 1: Fix needed. Round 2: Converged.
    report_fix = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="Docker",
                must_have=True,
                verdict="missing",
                route="fix",
                support=["Containerized services"]
            )
        ],
        summary="Fix with Docker bullet"
    )
    report_converged = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="Docker",
                must_have=True,
                verdict="covered",
                route="drop",
                support=["Containerized services"]
            )
        ],
        summary="All covered"
    )

    mock_critic = MagicMock()
    mock_critic.run.side_effect = [report_fix, report_converged]

    mock_writer = MagicMock()
    mock_writer.run_round.return_value = (
        {"work": [{"company": "Tech Corp", "highlights": ["Built Go services", "Containerized with Docker"]}]},
        {"edits": [{"section": "work", "action": "add"}], "summary": "Added Docker bullet"}
    )

    mock_docgen = MagicMock()
    mock_docgen.generate.return_value = "data/resumes/job_fix_converge/resume.pdf"

    process_evidence_loop(session, mock_critic, mock_writer, doc_generator=mock_docgen)

    session.refresh(job)
    assert job.state == JobState.DRAFTED
    assert job.cv_path == "data/resumes/job_fix_converge/resume.pdf"
    mock_docgen.generate.assert_called_once()
