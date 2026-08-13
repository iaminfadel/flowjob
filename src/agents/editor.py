import os
import fitz
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from src.agents.runner import AgentRunner
from src.utils.resume_parser import get_safe_resume_data

class EditorScore(BaseModel):
    score: int = Field(description="Score from 0 to 100 based on keyword coverage and formatting.")
    passed: bool = Field(description="True if the resume passes the QA, False otherwise. Should be True if score >= 80.")
    feedback: str = Field(description="Actionable feedback for the Tailor Agent if it failed, else empty string.")

class EditorAgent(AgentRunner):
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        self.model_name = model_name
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    def run(self, jd_text: str, pdf_path: str, resume_path: str = "master_resume.md") -> EditorScore:
        """
        Audits the extracted text from the Tailor's PDF against the JD and safe master resume.
        """
        # 1. Extract text from the PDF
        doc = fitz.open(pdf_path)
        extracted_text = ""
        for page in doc:
            extracted_text += page.get_text()
        doc.close()
        
        # 2. Get safe data to verify no hallucinations
        safe_resume = get_safe_resume_data(resume_path)
        
        # 3. Prompt Gemini
        prompt = f"""
You are an expert QA Editor for technical resumes. 
Your job is to audit the tailored resume against the Job Description and the candidate's original resume data.

Job Description:
{jd_text}

Candidate's Original Safe Resume Data:
{safe_resume.model_dump_json(indent=2)}

Extracted Text from Tailored Resume PDF:
{extracted_text}

Tasks:
1. Verify keyword coverage: Does the tailored resume include important keywords from the JD?
2. Fact-check: Does the tailored resume accurately reflect the original resume without hallucinating new jobs, skills, or degrees not in the original?
3. Grammar & Formatting: Is the text professional and well-formatted?

Score the resume from 0 to 100. If the score is below 80, set passed=False and provide specific, actionable feedback for the Tailor Agent to improve the next iteration. If passed=True, feedback can be empty.
"""
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EditorScore,
                temperature=0.1,
            ),
        )
        
        return response.parsed
