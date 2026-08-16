import pytest
import os
from unittest.mock import MagicMock, patch
from sqlmodel import create_engine, Session, SQLModel, select
from src.db.models import Job, JobState, FitScore
from src.pipeline.orchestrator import (
    process_new_jobs,
    process_analyzed_jobs,
    process_evidence_loop,
    process_drafted_jobs,
    process_edited_jobs,
    save_draft_json,
    load_draft_json
)
from src.agents.coverage_critic import CoverageReport, RequirementCheck
from src.agents.interviewer import run_grilling_session
from src.agents.editor import EditorScore

@pytest.fixture
def test_db_session(tmp_path):
    db_file = tmp_path / "test_flowjob.db"
    engine = create_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@pytest.fixture
def mock_doc_generator(tmp_path):
    generator = MagicMock()
    def fake_generate(draft_data, metadata, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        pdf_path = os.path.join(output_dir, "resume.pdf")
        with open(pdf_path, "w") as f:
            f.write("%PDF-1.4 fake resume content")
        return pdf_path
    generator.generate.side_effect = fake_generate
    return generator

def test_evidence_loop_happy_path_e2e(test_db_session, mock_doc_generator):
    session = test_db_session
    
    # 1. Start with a NEW job
    job = Job(
        id="job_e2e_1",
        url="http://example.com/job1",
        title="Senior Python Engineer",
        company="PyCorp",
        location="Remote",
        posted_date="2024-01-01",
        jd_text="Must know Python, FastAPI, and Kubernetes",
        state=JobState.NEW
    )
    session.add(job)
    session.commit()

    # 2. Analyst Step
    mock_analyst = MagicMock()
    mock_analyst.run.return_value = FitScore(
        score=85,
        matching_skills=["Python", "FastAPI"],
        missing_skills=["Kubernetes"],
        recommendation="apply"
    )
    config = {"analyst": {"min_fit_score": 70}}
    process_new_jobs(session, config, mock_analyst)
    
    session.refresh(job)
    assert job.state == JobState.ANALYZED
    assert job.fit_score == 85

    # 3. Tailor Step (Draft JSON created)
    mock_tailor = MagicMock()
    mock_tailor.run.return_value = {
        "basics": {"name": "Test Candidate"},
        "summary": "Experienced Python Engineer",
        "skills": [{"category": "Languages", "items": ["Python", "FastAPI"]}],
        "work": [{"company": "PrevCo", "highlights": ["Built FastAPI microservices"]}]
    }
    process_analyzed_jobs(session, mock_tailor, doc_generator=mock_doc_generator)
    
    session.refresh(job)
    assert job.state == JobState.DRAFTED
    draft_data = load_draft_json(job.id)
    assert "FastAPI" in str(draft_data)

    # 4. Evidence Loop: Critic finds missing K8s bullet -> Writer fixes from bank -> Critic confirms covered -> PDF generated
    mock_critic = MagicMock()
    report_fix = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="Kubernetes",
                must_have=True,
                verdict="missing",
                route="fix",
                support=[]
            )
        ],
        summary="Need K8s bullet from bank."
    )
    report_converged = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="Kubernetes",
                must_have=True,
                verdict="covered",
                route="drop",
                support=["Scaled Kubernetes clusters in production"]
            )
        ],
        summary="All requirements covered."
    )
    mock_critic.run.side_effect = [report_fix, report_converged]

    mock_writer = MagicMock()
    mock_writer.run_round.return_value = (
        {
            "basics": {"name": "Test Candidate"},
            "summary": "Experienced Python Engineer",
            "skills": [{"category": "Languages", "items": ["Python", "FastAPI", "Kubernetes"]}],
            "work": [{"company": "PrevCo", "highlights": ["Built FastAPI microservices", "Scaled Kubernetes clusters in production"]}]
        },
        {"edits": [{"section": "work", "action": "add"}], "summary": "Added K8s bullet from bank."}
    )

    process_evidence_loop(session, mock_critic, mock_writer, doc_generator=mock_doc_generator)
    
    session.refresh(job)
    assert job.state == JobState.DRAFTED
    assert job.cv_path.endswith("resume.pdf")
    assert os.path.exists(job.cv_path)

    # 5. Editor Step
    mock_editor = MagicMock()
    mock_editor.run.return_value = EditorScore(
        score=95,
        passed=True,
        feedback="Excellent resume with verified evidence"
    )
    process_drafted_jobs(session, mock_editor, doc_generator=mock_doc_generator)
    
    session.refresh(job)
    assert job.state == JobState.EDITED

    # 6. Edited -> Pending Approval
    process_edited_jobs(session)
    session.refresh(job)
    assert job.state == JobState.PENDING_APPROVAL

def test_evidence_loop_unfixable_e2e(test_db_session, mock_doc_generator):
    session = test_db_session
    job = Job(
        id="job_e2e_unfix",
        url="http://example.com/job_unfix",
        title="Cleared Security Architect",
        company="DefenseTech",
        location="Onsite",
        posted_date="2024-01-01",
        jd_text="Requires Active Top Secret SCI Clearance",
        state=JobState.DRAFTED
    )
    session.add(job)
    session.commit()
    save_draft_json(job.id, {"work": []})

    mock_critic = MagicMock()
    mock_critic.run.return_value = CoverageReport(
        unfixable=True,
        requirements=[
            RequirementCheck(
                requirement="Top Secret Clearance",
                must_have=True,
                verdict="missing",
                route="drop",
                note="Candidate has no clearance record."
            )
        ],
        summary="Unfixable missing clearance"
    )
    mock_writer = MagicMock()

    process_evidence_loop(session, mock_critic, mock_writer, doc_generator=mock_doc_generator)

    session.refresh(job)
    assert job.state == JobState.UNFIXABLE

def test_evidence_loop_grilling_resume_e2e(test_db_session, mock_doc_generator):
    session = test_db_session
    job = Job(
        id="job_e2e_grill",
        url="http://example.com/job_grill",
        title="Staff Rust Engineer",
        company="RustWorks",
        location="Remote",
        posted_date="2024-01-01",
        jd_text="Must have 3+ years production Rust",
        state=JobState.DRAFTED
    )
    session.add(job)
    session.commit()
    save_draft_json(job.id, {"work": [{"company": "Tech Corp", "highlights": []}]})

    # Step 1: Watch mode evidence loop encounters gap needing grilling
    mock_critic = MagicMock()
    mock_critic.run.return_value = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="Production Rust",
                must_have=True,
                verdict="missing",
                route="grill",
                support=[]
            )
        ],
        summary="Candidate lacks Rust in resume and bank"
    )
    mock_writer = MagicMock()

    process_evidence_loop(session, mock_critic, mock_writer, doc_generator=mock_doc_generator)

    session.refresh(job)
    assert job.state == JobState.NEEDS_EVIDENCE
    assert "Production Rust" in job.grilling_transcript["gaps"]

    # Step 2: Human conducts grilling session via CLI
    answers = [
        "I built high-throughput financial trading services in Rust for 2 years.",
        "We processed 500,000 req/sec at sub-millisecond p99 latency.",
        "y"  # Confirm bullet
    ]
    ans_iter = iter(answers)
    def mock_input(p=""):
        return next(ans_iter)

    success = run_grilling_session(
        session=session,
        job_id=job.id,
        input_fn=mock_input,
        interactive=True
    )
    assert success

    session.refresh(job)
    assert job.state == JobState.DRAFTED
    assert job.grilling_transcript["gaps"]["Production Rust"]["status"] == "completed"

    # Step 3: Pipeline re-runs evidence loop and now converges
    mock_critic.run.return_value = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="Production Rust",
                must_have=True,
                verdict="covered",
                route="drop",
                support=["Built high-throughput Rust services"]
            )
        ],
        summary="Covered via grilling bullet"
    )

    process_evidence_loop(session, mock_critic, mock_writer, doc_generator=mock_doc_generator)

    session.refresh(job)
    assert job.state == JobState.DRAFTED
    assert job.cv_path.endswith("resume.pdf")

def test_cli_commands_e2e(tmp_path):
    from typer.testing import CliRunner
    from src.cli import app

    runner = CliRunner()
    
    # 1. Test validate command
    val_res = runner.invoke(app, ["validate"])
    assert val_res.exit_code == 0
    assert "Validation complete" in val_res.stdout

    # 2. Test status command
    stat_res = runner.invoke(app, ["status"])
    assert stat_res.exit_code == 0
    assert "FlowJob Status" in stat_res.stdout
    assert "NEEDS_EVIDENCE" in stat_res.stdout
    assert "UNFIXABLE" in stat_res.stdout

    # 3. Test grill command with no args (listing)
    grill_res = runner.invoke(app, ["grill"])
    assert grill_res.exit_code == 0
