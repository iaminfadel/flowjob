from typing import Literal, Optional, List, Callable
from pydantic import BaseModel, Field
from src.agents.structured_llm import LangChainStructuredAgent
from src.utils.projection import project_resume_to_markdown
from src.utils.resume_parser import parse_master_resume

class RequirementCheck(BaseModel):
    requirement: str
    must_have: bool = True
    verdict: Literal["covered", "partially_covered", "missing"]
    route: Literal["fix", "grill", "drop"]
    support: list[str] = Field(default_factory=list)
    note: str = ""

class CoverageReport(BaseModel):
    unfixable: bool = False
    requirements: list[RequirementCheck] = Field(default_factory=list)
    summary: str = ""

CRITIC_PROMPT_TEMPLATE = """
You are an expert technical interviewer and resume critic.
Analyze the drafted resume against the target job description requirements and the master resume bullet bank.

Job Description:
{jd_text}

Draft Resume (Markdown):
{draft_markdown}

Master Resume Bullet Bank:
{bank_bullets}

Instructions:
1. Extract all key requirements and responsibilities from the Job Description.
2. Apply the SUBSTANTIVE-EVIDENCE rule:
   - "covered": The draft contains concrete, verifiable experience/skills backing the requirement.
   - "partially_covered": Mentioned weakly or missing key metric/depth.
   - "missing": Not addressed in the draft resume.
3. Route each requirement:
   - route="fix": If missing or partially covered, and the master bullet bank contains evidence that can be added/swapped.
   - route="grill": If missing or partially covered, not in bank, but is a reasonable must-have requirement that candidate may have experience with to interview about.
   - route="drop": If optional, nice-to-have, or minor preference that should not block the application.
4. If a critical MUST-HAVE requirement cannot be satisfied (e.g. candidate has 1 year experience for a role requiring 10+ years, or requires security clearance candidate cannot obtain), set unfixable=True.
"""

def critic_preprocessor(context: dict) -> dict:
    if "draft_markdown" not in context and "draft_data" in context:
        context["draft_markdown"] = project_resume_to_markdown(context["draft_data"])
    if "bank_bullets" not in context:
        try:
            _, md_content = parse_master_resume(context.get("master_resume_path", "master_resume.md"))
            context["bank_bullets"] = md_content
        except Exception:
            context["bank_bullets"] = ""
    return context

def CoverageCriticAgent(
    model_name: str = "google/gemini-2.5-pro",
    openrouter_base_url: str = "https://openrouter.ai/api/v1",
    openrouter_api_key: str = None
) -> LangChainStructuredAgent:
    return LangChainStructuredAgent(
        prompt_template=CRITIC_PROMPT_TEMPLATE,
        response_schema=CoverageReport,
        temperature=0.1,
        preprocessors=[critic_preprocessor],
        model_name=model_name,
        openrouter_base_url=openrouter_base_url,
        openrouter_api_key=openrouter_api_key
    )
