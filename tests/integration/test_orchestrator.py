import pytest
from sqlmodel import Session, SQLModel, create_engine
from unittest.mock import patch, MagicMock
from src.db.models import Job, JobState
from src.pipeline.orchestrator import run_pipeline

class FakeAgent:
    def __init__(self, name):
        self.name = name

    def run(self, *args, **kwargs):
        if self.name == "analyst":
            class FitScore:
                score = 80
                recommendation = "apply"
            return FitScore()
        elif self.name == "tailor":
            return {"basics": {"name": "Test"}}
        elif self.name == "editor":
            class EditScore:
                passed = True
                score = 95
                feedback = []
            return EditScore()
        elif self.name == "applicator":
            return True

@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@patch("src.pipeline.orchestrator.save_draft_json", return_value="fake_resume.json")
@patch("src.pipeline.orchestrator.load_draft_json", return_value={"basics": {"name": "Test"}})
@patch("src.pipeline.orchestrator.process_scout")
@patch("src.pipeline.orchestrator.prompt_user_approval", return_value=True)
@patch("src.pipeline.orchestrator.init_db")
@patch("src.pipeline.orchestrator.get_session")
@patch("src.tools.browser.check_session_health", return_value=True)
@patch("src.pipeline.orchestrator.yaml.safe_load")
@patch("builtins.open")
@patch("os.path.exists", return_value=True)
@patch("src.utils.document_generator.PlaywrightDocumentGenerator")
@patch("src.utils.resume_parser.parse_master_resume")
def test_full_pipeline_sequence(
    mock_parse, mock_docgen, mock_exists, mock_open, mock_yaml, mock_check, mock_get_session, mock_init_db, mock_prompt, mock_scout, mock_load_draft, mock_save_draft, session
):
    mock_yaml.return_value = {"analyst": {"min_fit_score": 70}, "data": {"db_path": "memory"}}
    mock_get_session.return_value.__enter__.return_value = session
    mock_metadata = MagicMock()
    mock_parse.return_value = (mock_metadata, "")
    
    mock_generator = MagicMock()
    mock_generator.generate.return_value = "fake_path.pdf"
    mock_docgen.return_value = mock_generator

    job = Job(id="1", title="SE", company="Co", url="http", location="Remote", posted_date="today", jd_text="test jd", state=JobState.NEW)
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
