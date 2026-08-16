import pytest
from unittest.mock import MagicMock
from sqlmodel import create_engine, Session, SQLModel
from src.db.models import Job, JobState
from src.agents.interviewer import (
    SynthesizedSTARBullet,
    generate_interview_question,
    synthesize_star_bullet,
    run_grilling_session
)
from src.pipeline.orchestrator import save_draft_json, load_draft_json

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_generate_interview_question():
    q = generate_interview_question("Kubernetes", [])
    assert "Kubernetes" in q

def test_synthesize_star_bullet():
    turns = [
        {"role": "interviewer", "text": "What did you do with Kubernetes?"},
        {"role": "candidate", "text": "I migrated our monolithic services to EKS clusters."}
    ]
    bullet = synthesize_star_bullet("Kubernetes", turns)
    assert isinstance(bullet, SynthesizedSTARBullet)
    assert "Kubernetes" in bullet.bullet

def test_run_grilling_session_resolves_gap(session, tmp_path):
    output_dir = str(tmp_path / "resumes")
    job = Job(
        id="job100",
        url="http://example.com",
        title="Senior Backend Engineer",
        company="CloudCo",
        location="Remote",
        posted_date="2023-01-01",
        jd_text="Must know Go and Kubernetes",
        state=JobState.NEEDS_EVIDENCE,
        grilling_transcript={
            "active_requirement": "Kubernetes",
            "gaps": {
                "Kubernetes": {"turns": [], "status": "pending"}
            }
        }
    )
    session.add(job)
    session.commit()

    save_draft_json("job100", {"work": [{"company": "Tech Inc", "highlights": []}]})

    # Simulated candidate responses
    responses = [
        "I managed a 20-node Kubernetes cluster hosting 40 microservices.",
        "We reduced deployment latency by 50% and achieved 99.99% uptime.",
        "y"  # Confirm proposed bullet
    ]
    input_iter = iter(responses)
    def mock_input_fn(prompt=""):
        return next(input_iter)

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="What actions did you take with Kubernetes?")

    success = run_grilling_session(
        session=session,
        job_id="job100",
        input_fn=mock_input_fn,
        interactive=True,
        llm=mock_llm
    )

    assert success
    session.refresh(job)
    assert job.state == JobState.DRAFTED
    assert job.grilling_transcript["gaps"]["Kubernetes"]["status"] == "completed"
