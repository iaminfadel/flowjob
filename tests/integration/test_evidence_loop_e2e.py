"""Evidence-loop behaviour through the PipelineCycleEngine interface.

Real in-memory SQLite, fake agents, InMemoryDocumentStore — mocks only at the
true external seams. These tests exercise the same stage code production runs.
"""

import pytest
from unittest.mock import MagicMock
from sqlmodel import create_engine, Session, SQLModel
from src.db.models import Job, JobState, FitScore
from src.pipeline.engine import PipelineCycleEngine
from src.pipeline.orchestrator import save_draft_json, load_draft_json
from src.storage.document_store import DiskDocumentStore
from src.agents.coverage_critic import CoverageReport, RequirementCheck
from src.agents.interviewer import run_grilling_session
from src.agents.editor import EditorScore


class FakeDocStore(DiskDocumentStore):
    """Disk drafts (so grilling transcripts work) but fake PDF compilation."""

    def compile_document(self, job_id, metadata, draft_data=None):
        import os

        job_dir = self._job_dir(job_id)
        os.makedirs(job_dir, exist_ok=True)
        if draft_data is not None:
            self.save_draft(job_id, draft_data)
        pdf_path = os.path.join(job_dir, "resume.pdf")
        with open(pdf_path, "w") as f:
            f.write("%PDF-1.4 fake resume content")
        return pdf_path


@pytest.fixture
def session(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def doc_store(tmp_path):
    return FakeDocStore(base_dir=str(tmp_path / "resumes"))


def make_engine(agents, doc_store, **kwargs):
    defaults = dict(
        config={"analyst": {"min_fit_score": 70}},
        agents=agents,
        doc_store=doc_store,
        notify_fn=lambda title, msg: None,
    )
    defaults.update(kwargs)
    return PipelineCycleEngine(**defaults)


def test_evidence_loop_happy_path_e2e(session, doc_store):
    # 1. Start with a NEW job
    job = Job(
        id="job_e2e_1",
        url="http://example.com/job1",
        title="Senior Python Engineer",
        company="PyCorp",
        location="Remote",
        posted_date="2024-01-01",
        jd_text="Must know Python, FastAPI, and Kubernetes",
        state=JobState.NEW,
    )
    session.add(job)
    session.commit()

    # 2. Analyst stage
    mock_analyst = MagicMock()
    mock_analyst.run.return_value = FitScore(
        score=85,
        matching_skills=["Python", "FastAPI"],
        missing_skills=["Kubernetes"],
        recommendation="apply",
    )
    engine = make_engine({"analyst": mock_analyst}, doc_store)
    assert engine.process_new_jobs(session) is True

    session.refresh(job)
    assert job.state == JobState.ANALYZED
    assert job.fit_score == 85

    # 3. Tailor stage (draft JSON created)
    mock_tailor = MagicMock()
    mock_tailor.run.return_value = {
        "basics": {"name": "Test Candidate"},
        "summary": "Experienced Python Engineer",
        "skills": [{"category": "Languages", "items": ["Python", "FastAPI"]}],
        "work": [{"company": "PrevCo", "highlights": ["Built FastAPI microservices"]}],
    }
    engine = make_engine({"tailor": mock_tailor}, doc_store)
    assert engine.process_analyzed_jobs(session) is True

    session.refresh(job)
    assert job.state == JobState.DRAFTED
    draft_data = load_draft_json(job.id, output_dir=doc_store.base_dir)
    assert "FastAPI" in str(draft_data)

    # 4. Evidence loop: critic finds missing K8s bullet -> writer fixes ->
    #    critic confirms covered -> PDF compiled
    report_fix = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="Kubernetes", must_have=True, verdict="missing", route="fix", support=[]
            )
        ],
        summary="Need K8s bullet from bank.",
    )
    report_converged = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="Kubernetes",
                must_have=True,
                verdict="covered",
                route="drop",
                support=["Scaled Kubernetes clusters in production"],
            )
        ],
        summary="All requirements covered.",
    )
    mock_critic = MagicMock()
    mock_critic.run.side_effect = [report_fix, report_converged]

    mock_writer = MagicMock()
    mock_writer.run_round.return_value = (
        {
            "basics": {"name": "Test Candidate"},
            "summary": "Experienced Python Engineer",
            "skills": [{"category": "Languages", "items": ["Python", "FastAPI", "Kubernetes"]}],
            "work": [
                {
                    "company": "PrevCo",
                    "highlights": ["Built FastAPI microservices", "Scaled Kubernetes clusters in production"],
                }
            ],
        },
        {"edits": [{"section": "work", "action": "add"}], "summary": "Added K8s bullet from bank."},
    )

    engine = make_engine({"critic": mock_critic, "writer": mock_writer}, doc_store)
    assert engine.process_evidence_loop(session) is True

    session.refresh(job)
    assert job.state == JobState.DRAFTED
    assert job.cv_path.endswith("resume.pdf")
    assert os.path.exists(job.cv_path)

    # 5. Editor stage
    mock_editor = MagicMock()
    mock_editor.run.return_value = EditorScore(
        score=95, passed=True, feedback="Excellent resume with verified evidence"
    )
    engine = make_engine({"editor": mock_editor}, doc_store)
    assert engine.process_drafted_jobs(session) is True

    session.refresh(job)
    assert job.state == JobState.EDITED

    # 6. Edited -> Pending Approval
    engine.process_edited_jobs(session)
    session.refresh(job)
    assert job.state == JobState.PENDING_APPROVAL


import os  # noqa: E402 — used by the happy-path assertion above


def test_evidence_loop_unfixable_e2e(session, doc_store):
    job = Job(
        id="job_e2e_unfix",
        url="http://example.com/job_unfix",
        title="Cleared Security Architect",
        company="DefenseTech",
        location="Onsite",
        posted_date="2024-01-01",
        jd_text="Requires Active Top Secret SCI Clearance",
        state=JobState.DRAFTED,
    )
    session.add(job)
    session.commit()
    doc_store.save_draft(job.id, {"work": []})

    mock_critic = MagicMock()
    mock_critic.run.return_value = CoverageReport(
        unfixable=True,
        requirements=[
            RequirementCheck(
                requirement="Top Secret Clearance",
                must_have=True,
                verdict="missing",
                route="drop",
                note="Candidate has no clearance record.",
            )
        ],
        summary="Unfixable missing clearance",
    )
    mock_writer = MagicMock()

    engine = make_engine({"critic": mock_critic, "writer": mock_writer}, doc_store)
    assert engine.process_evidence_loop(session) is True

    session.refresh(job)
    assert job.state == JobState.UNFIXABLE


def test_evidence_loop_grilling_resume_e2e(session, doc_store):
    job = Job(
        id="job_e2e_grill",
        url="http://example.com/job_grill",
        title="Staff Rust Engineer",
        company="RustWorks",
        location="Remote",
        posted_date="2024-01-01",
        jd_text="Must have 3+ years production Rust",
        state=JobState.DRAFTED,
    )
    session.add(job)
    session.commit()
    doc_store.save_draft(job.id, {"work": [{"company": "Tech Corp", "highlights": []}]})

    # Step 1: Watch-mode evidence loop encounters gap needing grilling
    mock_critic = MagicMock()
    mock_critic.run.return_value = CoverageReport(
        unfixable=False,
        requirements=[
            RequirementCheck(
                requirement="Production Rust", must_have=True, verdict="missing", route="grill", support=[]
            )
        ],
        summary="Candidate lacks Rust in resume and bank",
    )
    mock_writer = MagicMock()

    engine = make_engine({"critic": mock_critic, "writer": mock_writer}, doc_store)
    assert engine.process_evidence_loop(session) is True

    session.refresh(job)
    assert job.state == JobState.NEEDS_EVIDENCE
    assert "Production Rust" in job.grilling_transcript["gaps"]

    # Step 2: Human conducts grilling session via CLI
    answers = [
        "I built high-throughput financial trading services in Rust for 2 years.",
        "We processed 500,000 req/sec at sub-millisecond p99 latency.",
        "y",  # Confirm bullet
    ]
    ans_iter = iter(answers)

    def mock_input(p=""):
        return next(ans_iter)

    success = run_grilling_session(
        session=session,
        job_id=job.id,
        input_fn=mock_input,
        interactive=True,
        doc_store=doc_store,
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
                support=["Built high-throughput Rust services"],
            )
        ],
        summary="Covered via grilling bullet",
    )

    assert engine.process_evidence_loop(session) is True

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
