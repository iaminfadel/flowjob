import pytest
from sqlmodel import Session, SQLModel, create_engine
from unittest.mock import patch, MagicMock
from src.db.models import Job, JobState
from src.pipeline.orchestrator import run_pipeline

class FakeAgent:
    def __init__(self, name, should_fail=False):
        self.name = name
        self.should_fail = should_fail
        self.call_count = 0

    def run(self, *args, **kwargs):
        self.call_count += 1
        if self.name == "editor":
            class EditScore:
                passed = not self.should_fail
                score = 95
                feedback = "fix it"
            return EditScore()
        elif self.name == "tailor":
            return {"basics": {"name": "Test"}}
        elif self.name == "analyst":
            class FitScore:
                score = 80
                recommendation = "apply"
            return FitScore()
        elif self.name == "applicator":
            return not self.should_fail

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@patch("src.pipeline.orchestrator.save_draft_json", return_value="fake_resume.json")
@patch("src.pipeline.orchestrator.load_draft_json", return_value={"basics": {"name": "Test"}})
@patch("src.pipeline.orchestrator.process_scout")
@patch("src.pipeline.orchestrator.init_db")
@patch("src.pipeline.orchestrator.get_session")
@patch("src.tools.browser.check_session_health", return_value=True)
@patch("src.pipeline.orchestrator.yaml.safe_load")
@patch("builtins.open")
@patch("os.path.exists", return_value=True)
@patch("src.utils.document_generator.PlaywrightDocumentGenerator")
@patch("src.utils.resume_parser.parse_master_resume")
def test_editor_retry_max_retries(
    mock_parse, mock_docgen, mock_exists, mock_open, mock_yaml, mock_check, mock_get_session, mock_init_db, mock_scout, mock_load_draft, mock_save_draft, session
):
    mock_yaml.return_value = {"analyst": {"min_fit_score": 70}, "data": {"db_path": "memory"}}
    mock_get_session.return_value.__enter__.return_value = session
    mock_parse.return_value = (MagicMock(), "")
    
    mock_generator = MagicMock()
    mock_generator.generate.return_value = "fake_path.pdf"
    mock_docgen.return_value = mock_generator

    # Seed job in DRAFTED state
    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.DRAFTED)
    session.add(job)
    session.commit()

    agents = {
        "analyst": FakeAgent("analyst"),
        "tailor": FakeAgent("tailor"),
        "editor": FakeAgent("editor", should_fail=True),
        "applicator": FakeAgent("applicator")
    }

    # Run 1: Editor fails, transitions to ANALYZED, metadata set
    run_pipeline(agents, dry_run=False)
    session.refresh(job)
    assert job.state == JobState.ANALYZED
    # If job starts DRAFTED, Editor runs -> fails -> ANALYZED.
    # But process_analyzed_jobs already ran before process_drafted_jobs in the loop!
    # So it stays ANALYZED until the NEXT run_pipeline!

    assert job.state == JobState.ANALYZED
    assert job.tailor_metadata["retries"] == 1
    assert job.tailor_metadata["feedback"] == "fix it"

    # Run 2: Tailor runs -> DRAFTED, Editor runs -> fails -> EDIT_FAIL (max retries reached)
    run_pipeline(agents, dry_run=False)
    session.refresh(job)
    assert job.state == JobState.EDIT_FAIL

@patch("src.pipeline.orchestrator.process_scout")
@patch("src.pipeline.orchestrator.prompt_user_approval")
@patch("src.pipeline.orchestrator.init_db")
@patch("src.pipeline.orchestrator.get_session")
@patch("src.tools.browser.check_session_health", return_value=True)
@patch("src.pipeline.orchestrator.yaml.safe_load")
@patch("builtins.open")
def test_approval_acceptance_invokes_applicator(
    mock_open, mock_yaml, mock_check, mock_get_session, mock_init_db, mock_prompt, mock_scout, session
):
    mock_yaml.return_value = {"analyst": {"min_fit_score": 70}, "data": {"db_path": "memory"}}
    mock_get_session.return_value.__enter__.return_value = session
    mock_prompt.return_value = True # Accept!

    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.PENDING_APPROVAL)
    session.add(job)
    session.commit()

    agents = {
        "analyst": FakeAgent("analyst"),
        "tailor": FakeAgent("tailor"),
        "editor": FakeAgent("editor"),
        "applicator": FakeAgent("applicator")
    }

    run_pipeline(agents, dry_run=False)
    session.refresh(job)
    assert job.state == JobState.APPLIED
    assert agents["applicator"].call_count == 1

@patch("src.pipeline.orchestrator.process_scout")
@patch("src.pipeline.orchestrator.prompt_user_approval")
@patch("src.pipeline.orchestrator.init_db")
@patch("src.pipeline.orchestrator.get_session")
@patch("src.tools.browser.check_session_health", return_value=True)
@patch("src.pipeline.orchestrator.yaml.safe_load")
@patch("builtins.open")
def test_approval_rejection_transitions_to_skipped(
    mock_open, mock_yaml, mock_check, mock_get_session, mock_init_db, mock_prompt, mock_scout, session
):
    mock_yaml.return_value = {"analyst": {"min_fit_score": 70}, "data": {"db_path": "memory"}}
    mock_get_session.return_value.__enter__.return_value = session
    mock_prompt.return_value = False # Reject!

    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.PENDING_APPROVAL)
    session.add(job)
    session.commit()

    agents = {
        "analyst": FakeAgent("analyst"),
        "tailor": FakeAgent("tailor"),
        "editor": FakeAgent("editor"),
        "applicator": FakeAgent("applicator")
    }

    run_pipeline(agents, dry_run=False)
    session.refresh(job)
    assert job.state == JobState.SKIPPED
    assert agents["applicator"].call_count == 0
