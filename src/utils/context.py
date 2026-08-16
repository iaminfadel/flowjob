"""Canonical prompt-context builders.

All agents share ONE stable candidate-context block so provider-side prompt
caching (OpenRouter implicit/automatic, Gemini implicit) can serve repeated
prefixes at 0.1-0.25x input price. Stable content always comes FIRST; the
job description and task-specific text come after.
"""
from __future__ import annotations

import yaml

from src.utils.resume_parser import parse_master_resume


def build_candidate_block(skills: dict, preferences: dict, experience_md: str, include_experience: bool = True) -> str:
    """Serialize the candidate's non-PII context into one deterministic block."""
    parts = ["CANDIDATE CONTEXT (read-only reference):", "", "## Skills"]
    parts.append(yaml.safe_dump(skills or {}, sort_keys=False, allow_unicode=True).strip())
    parts.append("")
    parts.append("## Preferences")
    parts.append(yaml.safe_dump(preferences or {}, sort_keys=False, allow_unicode=True).strip())
    if include_experience and experience_md:
        parts.append("")
        parts.append("## Experience Bullet Bank")
        parts.append(experience_md.strip())
    return "\n".join(parts)


def load_candidate_block(master_resume_path: str = "master_resume.md", include_experience: bool = True) -> str:
    """Build the canonical candidate block from the master resume."""
    metadata, md_content = parse_master_resume(master_resume_path)
    return build_candidate_block(metadata.skills, metadata.preferences, md_content, include_experience=include_experience)


def build_jd_section(jd_text: str) -> str:
    return "---\nJOB DESCRIPTION:\n" + jd_text.strip() + "\n---"