import os
import yaml
from google import genai
from google.genai import types
from src.db.models import FitScore
from src.utils.resume_parser import get_safe_resume_data
from src.agents.runner import AgentRunner

class AnalystAgent(AgentRunner):
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        self.model_name = model_name
        # Initialize AGY SDK / genai client
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    def run(self, jd_text: str, resume_path: str = "master_resume.md") -> FitScore:
        """
        Analyze a job description against the safe parts of the master resume.
        Returns a parsed FitScore Pydantic object.
        """
        safe_resume = get_safe_resume_data(resume_path)
        
        prompt = f"""
You are an expert technical recruiter analyzing a job posting against a candidate's profile.

Candidate Profile (No PII):
{yaml.dump(safe_resume.model_dump())}

Job Description:
{jd_text}

Analyze the fit and return a structured assessment. 
The score should be 0-100.
Score the job fit against the Master Resume AND the candidate's preferences config.
Identify matching skills from the candidate's profile that are required in the JD.
Identify missing skills that are required in the JD but not found in the profile.
Provide a recommendation: "apply", "skip", or "review".
"""
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FitScore,
                temperature=0.2,
            ),
        )
        
        return response.parsed
