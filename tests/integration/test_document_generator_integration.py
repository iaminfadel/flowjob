import os
from src.utils.document_generator import DocumentGenerator

class MockMetadata:
    name = "Test User"
    email = "test@example.com"

def test_document_generator_integration(tmp_path):
    generator = DocumentGenerator(template_dir="src/utils")
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
    
    pdf_path = generator.generate(resume_data, MockMetadata(), output_dir)
    
    assert os.path.exists(pdf_path)
    assert pdf_path == os.path.join(output_dir, "resume.pdf")
    assert os.path.exists(os.path.join(output_dir, "resume.html"))
    assert os.path.exists(os.path.join(output_dir, "resume.json"))
