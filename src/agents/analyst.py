from src.db.models import FitScore
from src.utils.resume_parser import get_safe_resume_data
from src.utils.context import build_candidate_block, build_jd_section
from src.agents.structured_llm import LangChainStructuredAgent

ANALYST_PROMPT_TEMPLATE = """
You are an expert technical recruiter analyzing a job posting against a candidate's profile.

{candidate_block}

{jd_section}

Analyze the fit and return a structured assessment. 
The score should be 0-100.
Score the job fit against the Master Resume AND the candidate's preferences config.
Identify matching skills from the candidate's profile that are required in the JD.
Identify missing skills that are required in the JD but not found in the profile.
Provide a recommendation: "apply", "skip", or "review".
"""

def analyst_preprocessor(context: dict) -> dict:
    safe_resume = get_safe_resume_data(context.get("resume_path", "master_resume.md"))
    context["candidate_block"] = build_candidate_block(safe_resume.skills, safe_resume.preferences, "", include_experience=False)
    context["jd_section"] = build_jd_section(context.get("jd_text", ""))
    return context

def AnalystAgent(model_name: str = "google/gemini-2.5-pro", openrouter_base_url: str = "https://openrouter.ai/api/v1", openrouter_api_key: str = None) -> LangChainStructuredAgent:
    return LangChainStructuredAgent(
        prompt_template=ANALYST_PROMPT_TEMPLATE,
        response_schema=FitScore,
        temperature=0.2,
        preprocessors=[analyst_preprocessor],
        model_name=model_name,
        openrouter_base_url=openrouter_base_url,
        openrouter_api_key=openrouter_api_key
    )
