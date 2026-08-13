import os
import json
from pathlib import Path
from typing import Optional, List, Dict
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

class TailorAgent(AgentRunner):
    def __init__(self, client, model_name: str = "gemini-2.5-pro"):
        self.model_name = model_name
        self.client = client

    def run(self, jd_text: str, resume_path: str = "master_resume.md", feedback: Optional[str] = None) -> dict:
        """
        Tailors the safe master resume for a specific JD, re-injects PII,
        and returns the tailored resume data as a dictionary.
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
        if feedback:
            prompt += f"\n\nFEEDBACK FROM PREVIOUS ATTEMPT (You MUST address this):\n{feedback}\n"
        
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

        return tailored_resume

