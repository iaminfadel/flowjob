import os
import json
import pytest
from src.utils.projection import project_resume_to_markdown
from src.pipeline.orchestrator import save_draft_json, load_draft_json

def test_project_resume_to_markdown():
    sample_resume = {
        "basics": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-1234",
            "location": "San Francisco, CA"
        },
        "summary": "Experienced Software Engineer with a focus on cloud native systems.",
        "skills": [
            {"category": "Languages", "items": ["Python", "Go"]},
            {"category": "Tools", "items": ["Docker", "Kubernetes"]}
        ],
        "work": [
            {
                "company": "Cloud Corp",
                "position": "Senior Engineer",
                "startDate": "2021",
                "endDate": "Present",
                "highlights": [
                    "Led migration to Kubernetes.",
                    "Improved latency by 20%."
                ]
            }
        ],
        "projects": [
            {
                "name": "FlowJob",
                "description": "Automated pipeline",
                "highlights": ["Built CLI with Typer"]
            }
        ],
        "education": [
            {
                "institution": "State University",
                "area": "Computer Science",
                "studyType": "B.S.",
                "date": "2016 - 2020"
            }
        ]
    }
    
    md = project_resume_to_markdown(sample_resume)
    assert "# Jane Doe" in md
    assert "jane@example.com | 555-1234 | San Francisco, CA" in md
    assert "## Summary" in md
    assert "Experienced Software Engineer" in md
    assert "## Skills" in md
    assert "**Languages**: Python, Go" in md
    assert "## Experience" in md
    assert "**Senior Engineer** | Cloud Corp | 2021 - Present" in md
    assert "- Led migration to Kubernetes." in md
    assert "## Projects" in md
    assert "**FlowJob**" in md
    assert "## Education" in md
    assert "**State University** | B.S. in Computer Science | 2016 - 2020" in md

def test_save_and_load_draft_json(tmp_path):
    output_dir = str(tmp_path / "resumes")
    job_id = "testjob123"
    data = {"basics": {"name": "Test User"}, "skills": []}
    
    file_path = save_draft_json(job_id, data, output_dir=output_dir)
    assert os.path.exists(file_path)
    assert file_path.endswith("resume.json")
    
    loaded = load_draft_json(job_id, output_dir=output_dir)
    assert loaded == data

def test_load_draft_json_missing_returns_empty(tmp_path):
    output_dir = str(tmp_path / "resumes")
    loaded = load_draft_json("nonexistent", output_dir=output_dir)
    assert loaded == {}
