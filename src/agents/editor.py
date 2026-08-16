import os
from pydantic import BaseModel, Field
from src.utils.resume_parser import get_safe_resume_data
from src.utils.context import build_candidate_block, build_jd_section
from src.utils.pdf_utils import extract_text_from_pdf
from src.agents.structured_llm import LangChainStructuredAgent

class EditorScore(BaseModel):
    score: int = Field(description="Score from 0 to 100 based on keyword coverage and formatting.")
    passed: bool = Field(description="True if the resume passes the QA, False otherwise. Should be True if score >= 80.")
    feedback: str = Field(description="Actionable feedback for the Tailor Agent if it failed, else empty string.")

EDITOR_PROMPT_TEMPLATE = """
You are an expert QA Editor for technical resumes. 
Your job is to audit the tailored resume against the Job Description and the candidate's original resume data.

{candidate_block}

{jd_section}

Extracted Text from Tailored Resume PDF:
{extracted_text}

Tasks:
1. Verify keyword coverage: Does the tailored resume include important keywords from the JD?
2. Fact-check: Does the tailored resume accurately reflect the original resume without hallucinating new jobs, skills, or degrees not in the original?
3. Tone Auditing & Grammar: Is the text professional, confident, and well-formatted without being overly boastful or grammatically incorrect?

Score the resume from 0 to 100. If the score is below 80, set passed=False and provide specific, actionable feedback for the Tailor Agent to improve the next iteration. If passed=True, feedback can be empty.
"""

def editor_preprocessor(context: dict) -> dict:
    context["extracted_text"] = extract_text_from_pdf(context["pdf_path"])
    safe_resume = get_safe_resume_data(context.get("resume_path", "master_resume.md"))
    context["candidate_block"] = build_candidate_block(safe_resume.skills, safe_resume.preferences, safe_resume.experience)
    context["jd_section"] = build_jd_section(context.get("jd_text", ""))
    return context

def EditorAgent(model_name: str = "google/gemini-2.5-pro", openrouter_base_url: str = "https://openrouter.ai/api/v1", openrouter_api_key: str = None) -> LangChainStructuredAgent:
    return LangChainStructuredAgent(
        prompt_template=EDITOR_PROMPT_TEMPLATE,
        response_schema=EditorScore,
        temperature=0.1,
        preprocessors=[editor_preprocessor],
        model_name=model_name,
        openrouter_base_url=openrouter_base_url,
        openrouter_api_key=openrouter_api_key
    )
