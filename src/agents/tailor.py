import os
import json
from pathlib import Path
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

from src.agents.runner import AgentRunner
from src.agents.structured_llm import LangChainStructuredAgent
from src.utils.resume_parser import get_safe_resume_data, parse_master_resume
from src.utils.context import build_candidate_block, build_jd_section

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

TAILOR_PROMPT_TEMPLATE = """
You are an expert technical recruiter and resume writer.
I have a job description and a candidate's master resume (without PII).
Select the most relevant experience, projects, and skills to tailor the resume for this job.
Limit the experience to the most relevant items, and re-write or select the highlights that best match the JD.
Make it concise and impactful. Return it matching the JSON Resume schema structure.

{candidate_block}

{jd_section}
{feedback_section}
"""

def tailor_preprocessor(context: dict) -> dict:
    safe_resume = get_safe_resume_data(context.get("resume_path", "master_resume.md"))
    context["candidate_block"] = build_candidate_block(safe_resume.skills, safe_resume.preferences, safe_resume.experience)
    context["jd_section"] = build_jd_section(context.get("jd_text", ""))
    feedback = context.get("feedback")
    if feedback:
        context["feedback_section"] = f"\n\nFEEDBACK FROM PREVIOUS ATTEMPT (You MUST address this):\n{feedback}\n"
    else:
        context["feedback_section"] = ""
    return context

class TailorAgent(AgentRunner):
    def __init__(self, model_name: str = "google/gemini-2.5-pro", openrouter_base_url: str = "https://openrouter.ai/api/v1", openrouter_api_key: str = None):
        super().__init__()
        self.structured_agent = LangChainStructuredAgent(
            prompt_template=TAILOR_PROMPT_TEMPLATE,
            response_schema=ResumeOutput,
            temperature=0.2,
            preprocessors=[tailor_preprocessor],
            model_name=model_name,
            openrouter_base_url=openrouter_base_url,
            openrouter_api_key=openrouter_api_key
        )

    def run(self, jd_text: str, resume_path: str = "master_resume.md", feedback: Optional[str] = None, job_id: str = "", agent_name: str = "TailorAgent") -> dict:
        """
        Tailors the safe master resume for a specific JD, re-injects PII,
        and returns the tailored resume data as a dictionary.
        """
        context = {
            "jd_text": jd_text,
            "resume_path": resume_path,
            "feedback": feedback
        }
        
        parsed_response = self.structured_agent.run(context, job_id=job_id, agent_name=agent_name)
        tailored_resume = parsed_response.model_dump()
        
        # 3. Re-inject PII
        metadata, _ = parse_master_resume(resume_path)
        tailored_resume["basics"] = {
            "name": metadata.name,
            "email": metadata.email,
            "phone": metadata.phone,
            "location": parse_location(metadata.location),
            "profiles": metadata.links
        }
        
        # Also inject education from metadata if the LLM didn't
        if not tailored_resume.get("education") and hasattr(metadata, "education"):
            tailored_resume["education"] = metadata.education

        return tailored_resume
