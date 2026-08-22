import os
import json
from pathlib import Path
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

from src.agents.runner import AgentRunner
from src.agents.structured_llm import LangChainStructuredAgent
from src.utils.latex_utils import as_model_dict
from src.utils.resume_parser import get_safe_resume_data, parse_master_resume
from src.utils.context import build_candidate_block, build_jd_section

# JSON Resume Schema Pydantic Models for GenAI
# Canonical key vocabulary mirrors master_resume.md frontmatter
# (degree / start_date / end_date) so LLM output cannot drift between
# provider runs — the LaTeX renderer normalizes defensively as well.
class Location(BaseModel):
    city: str = ""
    region: str = ""

class Profile(BaseModel):
    name: str = ""
    url: str = ""

class Basics(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: Optional[Location] = None
    profiles: List[Profile] = Field(default_factory=list)

class EducationItem(BaseModel):
    institution: str
    degree: str
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    gpa: str = ""

class WorkItem(BaseModel):
    name: str
    position: str
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    highlights: List[str] = Field(default_factory=list)

class ProjectItem(BaseModel):
    name: str
    technologies: str = ""
    description: str = ""
    start_date: str = ""
    end_date: str = ""
    highlights: List[str] = Field(default_factory=list)

class CertificateItem(BaseModel):
    year: str = ""
    title: str

class GraduationProject(BaseModel):
    title: str
    url: str = ""
    date_range: str = ""
    highlights: List[str] = Field(default_factory=list)

class SkillItem(BaseModel):
    name: str
    keywords: List[str]

class ResumeOutput(BaseModel):
    basics: Basics = Field(default_factory=Basics)
    summary: str = ""
    education: List[EducationItem] = Field(default_factory=list)
    graduation_project: Optional[GraduationProject] = None
    work: List[WorkItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    certificates: List[CertificateItem] = Field(default_factory=list)
    skills: List[SkillItem] = Field(default_factory=list)

def parse_location(location: str) -> dict:
    if "," in location:
        return {
            "city": location.split(",")[0].strip(),
            "region": location.split(",")[-1].strip()
        }
    return {"city": location}

TAILOR_PROMPT_TEMPLATE = """You are an expert technical resume writer who produces resumes indistinguishable from a senior engineer's hand-crafted LaTeX CV.
You tailor a master resume bank into a targeted resume for ONE job description. You select ruthlessly and write in the exact house style below.

## House style (NON-NEGOTIABLE — this is what accepted output looks like)

Bullet rules:
- Start every bullet with a strong past-tense action verb (Built, Designed, Developed, Led, Automated, Implemented, Directed, Owned). Present tense only for roles still ongoing ("Present" end date).
- Prefer bank bullets carrying hard numbers (%, counts, time reductions, team sizes, placements) when equally relevant — concrete evidence beats prose. Weave metrics in naturally; never invent them.
- Each bullet is 1–2 lines (~120–220 characters). Never longer. One idea per bullet.
- No first person, no articles at the start ("The", "A"), no filler adverbs ("successfully", "effectively").
- NO lead verb may repeat anywhere in the resume: if two bullets would both start with "Led", rewrite one to start with a different verb (Directed, Headed, Coordinated...).
- Strip any [bracket] tags from bank bullets before use — they are internal metadata, never render them.

Selection & weighting rules:
- EXPERIENCE IS THE BACKBONE. Include every professional/team experience relevant to the JD. The strongest match gets the deepest treatment (its best bullets); peripheral roles get progressively less. When in doubt between more experience or more projects, favor experience.
- ORDER: within each section, entries are strictly reverse-chronological by start date (newest first) — selection is by relevance, but ORDER is always by date, matching a hand-made CV.
- NEVER duplicate the Graduation Project in the projects list — it renders as its own section automatically.
- Projects supplement experience: include 4–6 projects that add evidence the experience section does not already cover, most JD-relevant first. Drop marginal ones rather than padding.
- Skills: build 5–7 groups whose names AND contents mirror the JD's own vocabulary (e.g. if the JD says "perception", a group named around perception beats a generic "AI" label). Each group carries 6–10 genuinely held keywords from the bank — dense one-to-two-line groups like a hand-crafted CV, never thin 3-item lists. Order groups by JD relevance, most relevant first.
- Certificates & awards: include ALL certificates/awards from the provided data unless one directly contradicts the JD's story. Preserve exact titles and years.
- Education: copy verbatim from the provided data, including GPA/honors line.

Field conventions (the renderer maps these straight onto the LaTeX layout):
- work items: "name" = ORGANIZATION exactly as spelled in the bank header, "position" = role title, "location" = the bank's location string. Copy org/role/location/dates VERBATIM from the bank headers — dates are factual and verified downstream; any drift is corrected by stripping your values.
- projects: "technologies" = SHORT comma-separated tech list ONLY (e.g. "Multi-Agent AI Pipeline, Python"). NEVER put a description sentence in technologies or description — descriptions belong in highlights as bullets.
- Do NOT create a skills group named "Languages": spoken languages are injected automatically as the final skills line.
- Include a 3–4 sentence "summary" Profile paragraph tailored to THIS job: highest qualification/honors first, then the most JD-relevant proof points (leadership, production experience, competition results — whatever the bank supports), then availability if known. Tone: precise, confident, factual. No buzzword soup. Mirror the JD's domain language.

One-page discipline:
- Target a FULL two-page layout like a hand-crafted CV (page 1: Profile through Experience; page 2: Projects, Certificates, Skills — well filled). Caps: max 5 work entries, 4–6 projects, max 3–4 bullets per entry (2 for peripheral roles). When trimming, cut the least JD-relevant content — never shrink bullet quality.
- GPA/honors phrasing must copy the bank exactly (e.g. "Class Rank 1st" style from the bank's profile base) — do not rephrase.

## Output contract

Return ONLY valid JSON matching the schema. Use EXACTLY these keys: education items use institution/degree/location/start_date/end_date/gpa; work and project items use name/position|technologies/location/start_date/end_date/highlights; dates are ISO "YYYY-MM" (or "YYYY"); end_date "Present" when ongoing. Do not invent employers, projects, skills, or degrees that are not in the candidate context. Do not include contact info — it is injected automatically.

{candidate_block}

{jd_section}
{feedback_section}
"""

def _static_sections_block(metadata) -> str:
    """Non-PII factual sections the Tailor may select from (never contact info)."""
    lines = ["## Static Sections (select per JD; copy titles/years verbatim)"]
    certs = getattr(metadata, "certificates_awards", None) or []
    if certs:
        lines.append("### Certificates & Awards")
        for cert in certs:
            cert_data = as_model_dict(cert)
            lines.append(f"- {cert_data.get('year', '')} -- {cert_data.get('title', '')}")
    gp = getattr(metadata, "graduation_project", None)
    if gp is not None:
        gp_data = as_model_dict(gp)
        if gp_data.get("title"):
            lines.append("### Graduation Project")
            lines.append(f"- {gp_data.get('title', '')} ({gp_data.get('date_range', '')})")
            for hl in gp_data.get("highlights", []):
                lines.append(f"  - {hl}")
    langs = getattr(metadata, "languages_spoken", None) or []
    if langs:
        lines.append(f"### Languages Spoken\n- {', '.join(langs)}")
    profile_base = getattr(metadata, "profile_base", "") or ""
    if profile_base:
        lines.append(f"### Profile Base (seed for the tailored Profile paragraph)\n{profile_base}")
    return "\n".join(lines)


def tailor_preprocessor(context: dict) -> dict:
    safe_resume = get_safe_resume_data(context.get("resume_path", "master_resume.md"))
    context["candidate_block"] = build_candidate_block(safe_resume.skills, safe_resume.preferences, safe_resume.experience)
    try:
        metadata, _ = parse_master_resume(context.get("resume_path", "master_resume.md"))
        static_block = _static_sections_block(metadata)
    except Exception:
        static_block = ""
    if static_block:
        context["candidate_block"] = f"{context['candidate_block']}\n\n{static_block}"
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
        
        # 3. Re-inject PII (never sent to the LLM)
        metadata, _ = parse_master_resume(resume_path)
        tailored_resume["basics"] = {
            "name": metadata.name,
            "email": metadata.email,
            "phone": metadata.phone,
            "location": parse_location(metadata.location),
            "profiles": [
                {"name": link.get("name", ""), "url": link.get("url", "")}
                for link in (metadata.links or [])
            ],
        }

        # Education is factual — always injected verbatim from metadata,
        # never trusted to LLM output (prevents date/GPA drift).
        if getattr(metadata, "education", None):
            tailored_resume["education"] = metadata.education

        return tailored_resume
