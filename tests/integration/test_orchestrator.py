import pytest
from unittest.mock import patch, MagicMock
from src.db.models import Job, JobState
from src.pipeline.orchestrator import process_analyzed_jobs, process_drafted_jobs

@patch("src.pipeline.orchestrator.TailorAgent")
@patch("src.pipeline.orchestrator.EditorAgent")
@patch("src.utils.document_generator.DocumentGenerator")
@patch("src.utils.resume_parser.parse_master_resume")
def test_tailor_docgen_editor_chain(mock_parse_master, mock_docgen_class, mock_editor_class, mock_tailor_class):
    # Setup mocks
    mock_tailor = MagicMock()
    mock_tailor.run.return_value = {"basics": {"name": "Test"}}
    mock_tailor_class.return_value = mock_tailor

    mock_metadata = MagicMock()
    mock_parse_master.return_value = (mock_metadata, "")

    mock_docgen = MagicMock()
    mock_docgen.generate.return_value = "fake_dir/resume.pdf"
    mock_docgen_class.return_value = mock_docgen

    mock_editor = MagicMock()
    mock_editor_score = MagicMock()
    mock_editor_score.passed = True
    mock_editor_score.score = 95
    mock_editor.run.return_value = mock_editor_score
    mock_editor_class.return_value = mock_editor

    # Mock DB session and Job
    mock_session = MagicMock()
    
    # 1. Test Tailor -> DocumentGenerator
    job = Job(id="job123", url="http", title="T", company="C", state=JobState.ANALYZED, jd_text="JD")
    mock_session.exec.return_value.all.return_value = [job]
    
    process_analyzed_jobs(mock_session)
    
    mock_tailor.run.assert_called_once()
    mock_docgen.generate.assert_called_once_with({"basics": {"name": "Test"}}, mock_metadata, "data/resumes/job123")
    assert job.state == JobState.DRAFTED
    assert job.cv_path == "fake_dir/resume.pdf"
    
    # 2. Test Editor
    job.state = JobState.DRAFTED
    mock_session.exec.return_value.all.return_value = [job]
    
    with patch("os.path.exists", return_value=True):
        process_drafted_jobs(mock_session)
        
    mock_editor.run.assert_called_once()
    # Editor uses the cv_path now or does it hardcode?
    # Wait, in orchestrator it currently hardcodes: pdf_path = os.path.join("data", "resumes", j.id, "resume.pdf")
    # I should check process_drafted_jobs to ensure it uses cv_path.
    assert job.state == JobState.EDITED

