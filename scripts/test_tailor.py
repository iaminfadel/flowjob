import os
import asyncio
from pathlib import Path

def test():
    print("Testing TailorAgent rendering and PDF...")
    
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_output"))
    os.makedirs(output_dir, exist_ok=True)
    
    # Mock LLM tailored output
    tailored_resume = {
        "basics": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-1234",
            "location": {"city": "New York", "region": "NY"},
            "profiles": [{"network": "LinkedIn", "url": "http://linkedin.com/in/jane"}]
        },
        "education": [
            {"institution": "University of XYZ", "area": "Computer Science", "studyType": "B.S.", "startDate": "2015", "endDate": "2019"}
        ],
        "work": [
            {"name": "Tech Corp", "position": "Software Engineer", "startDate": "2019", "endDate": "2023", "highlights": ["Built cool stuff", "Did python things"]}
        ],
        "projects": [
            {"name": "FlowJob", "description": "Agentic Pipeline", "startDate": "2023", "endDate": "Present", "highlights": ["Wrote agents", "Did PDF gen"]}
        ],
        "skills": [
            {"name": "Languages", "keywords": ["Python", "Java", "C++"]}
        ]
    }
    
    from src.utils.document_generator import DocumentGenerator
    from src.utils.resume_parser import ResumeMetadata

    metadata = ResumeMetadata(
        name="Jane Doe",
        title="Software Engineer",
        email="jane@example.com",
        phone="555-1234",
        location="New York, NY",
        links=[{"network": "LinkedIn", "url": "http://linkedin.com/in/jane"}],
        skills={},
        preferences={},
        personal_nudge={},
        education=[]
    )
    
    generator = DocumentGenerator()
    pdf_path = generator.generate(tailored_resume, metadata, output_dir)
        
    print(f"Success! PDF generated at: {pdf_path}")
    print(f"HTML is at: {os.path.join(output_dir, 'resume.html')}")
    print(f"JSON is at: {os.path.join(output_dir, 'resume.json')}")

if __name__ == "__main__":
    test()
