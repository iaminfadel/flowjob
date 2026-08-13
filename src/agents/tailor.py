import os
import json
from pathlib import Path
from typing import Optional, List, Dict
import fitz  # PyMuPDF
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from src.agents.runner import AgentRunner
from src.utils.resume_parser import get_safe_resume_data, parse_master_resume

# JSON Resume Schema Pydantic Models for GenAI
class Location(BaseModel):
    city: str = ""
    region: str = ""

class Profile(BaseModel):
    network: str = ""
    url: str = ""

class Basics(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: Optional[Location] = None
    profiles: List[Profile] = Field(default_factory=list)

class EducationItem(BaseModel):
    institution: str
    area: str
    studyType: str
    startDate: str
    endDate: str

class WorkItem(BaseModel):
    name: str
    position: str
    startDate: str
    endDate: str
    highlights: List[str]

class ProjectItem(BaseModel):
    name: str
    description: str
    startDate: str
    endDate: str
    highlights: List[str]

class SkillItem(BaseModel):
    name: str
    keywords: List[str]

class ResumeOutput(BaseModel):
    basics: Basics = Field(default_factory=Basics)
    education: List[EducationItem] = Field(default_factory=list)
    work: List[WorkItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    skills: List[SkillItem] = Field(default_factory=list)

def parse_location(location: str) -> dict:
    if "," in location:
        return {
            "city": location.split(",")[0].strip(),
            "region": location.split(",")[-1].strip()
        }
    return {"city": location}

def generate_resume_pdf(tailored_resume: dict, metadata, output_dir: str) -> str:
    """Renders the HTML and PDF for the given tailored resume dict."""
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Save JSON
    json_path = os.path.join(output_dir, "resume.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(tailored_resume, f, indent=2)

    # 2. Render HTML using Jinja2
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "utils")
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("resume_template.html")
    html_content = template.render(**tailored_resume)
    
    html_path = os.path.join(output_dir, "resume.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    # 3. Print PDF using Playwright
    pdf_path = os.path.join(output_dir, "resume.pdf")
    with sync_playwright() as p:
        # Playwright print-to-pdf requires headless=True
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # use absolute path for file:// url
        abs_html_path = Path(html_path).absolute()
        page.goto(f"file:///{abs_html_path}", wait_until="networkidle")
        page.pdf(path=pdf_path, format="A4", margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        browser.close()
        
    # 4. Validate ATS parseability with PyMuPDF
    doc = fitz.open(pdf_path)
    extracted_text = ""
    for page in doc:
        extracted_text += page.get_text()
    doc.close()
    
    if metadata.name not in extracted_text or metadata.email not in extracted_text:
        raise ValueError(f"Generated PDF at {pdf_path} failed ATS validation: contact info not found in extracted text.")
        
    return pdf_path

class TailorAgent(AgentRunner):
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        self.model_name = model_name
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    def run(self, jd_text: str, resume_path: str = "master_resume.md", output_dir: str = "output") -> str:
        """
        Tailors the safe master resume for a specific JD, generates HTML & PDF,
        validates PDF with PyMuPDF, and returns the path to the PDF.
        """
        # 1. Get safe data for LLM
        safe_resume = get_safe_resume_data(resume_path)
        
        # 2. Ask LLM to tailor the resume
        prompt = f"""
You are an expert technical recruiter and resume writer.
I have a job description and a candidate's master resume (without PII).
Select the most relevant experience, projects, and skills to tailor the resume for this job.
Limit the experience to the most relevant items, and re-write or select the highlights that best match the JD.
Make it concise and impactful. Return it matching the JSON Resume schema structure.

Job Description:
{jd_text}

Candidate's Safe Resume Data:
{safe_resume.model_dump_json(indent=2)}
"""
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ResumeOutput,
                temperature=0.2,
            ),
        )
        
        tailored_resume = response.parsed.model_dump()
        
        # 3. Re-inject PII
        metadata, _ = parse_master_resume(resume_path)
        tailored_resume["basics"] = {
            "name": metadata.name,
            "email": metadata.email,
            "phone": metadata.phone,
            "location": parse_location(metadata.location),
            "profiles": metadata.links
        }
        
        # Also inject education from metadata if the LLM didn't (often LLM drops it if not in safe_resume)
        if not tailored_resume.get("education") and hasattr(metadata, "education"):
            tailored_resume["education"] = metadata.education

        return generate_resume_pdf(tailored_resume, metadata, output_dir)
