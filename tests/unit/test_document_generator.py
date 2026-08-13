import os
from unittest.mock import patch, MagicMock
from src.utils.document_generator import PlaywrightDocumentGenerator

class MockMetadata:
    name = "Test User"
    email = "test@example.com"

def test_html_rendering_only(tmp_path):
    generator = PlaywrightDocumentGenerator(template_dir="src/utils")
    resume_data = {
        "basics": {
            "name": "Test User",
            "email": "test@example.com",
            "phone": "555-5555"
        },
        "education": [],
        "work": [],
        "projects": [],
        "skills": []
    }
    
    output_dir = str(tmp_path)
    
    with patch("src.utils.document_generator.sync_playwright") as mock_playwright:
        with patch("src.utils.document_generator.fitz.open") as mock_fitz:
            # Mock fitz so it passes ATS check
            mock_doc = MagicMock()
            mock_page = MagicMock()
            mock_page.get_text.return_value = "Test User test@example.com"
            mock_doc.__iter__.return_value = [mock_page]
            mock_fitz.return_value = mock_doc
            
            pdf_path = generator.generate(resume_data, MockMetadata(), output_dir)
            
            assert os.path.exists(os.path.join(output_dir, "resume.html"))
            assert os.path.exists(os.path.join(output_dir, "resume.json"))
            
            with open(os.path.join(output_dir, "resume.html"), "r") as f:
                html_content = f.read()
                assert "Test User" in html_content
                assert "test@example.com" in html_content
