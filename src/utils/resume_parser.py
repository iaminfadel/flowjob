from typing import Optional

import yaml
from pathlib import Path
from pydantic import BaseModel, Field, ValidationError

class GraduationProjectMeta(BaseModel):
    title: str = ""
    url: str = ""
    date_range: str = ""
    highlights: list[str] = Field(default_factory=list)

class CertificateMeta(BaseModel):
    year: str = ""
    title: str = ""

class ResumeMetadata(BaseModel):
    schema_version: str = "1"
    name: str
    full_name: str = ""
    title: str = ""
    email: str
    phone: str
    location: str
    links: list[dict] = Field(default_factory=list)
    skills: dict[str, list[str]] = Field(default_factory=dict)
    preferences: dict = Field(default_factory=dict)
    personal_nudge: dict = Field(default_factory=dict)
    education: list[dict] = Field(default_factory=list)
    # Gold-standard header/section extras (injected locally at render time,
    # never sent to LLMs — PII boundary).
    nationality: str = ""
    military_service: str = ""
    availability: str = ""
    languages_spoken: list[str] = Field(default_factory=list)
    certificates_awards: list[CertificateMeta] = Field(default_factory=list)
    graduation_project: Optional[GraduationProjectMeta] = None
    profile_base: str = ""

def parse_master_resume(path: str = "master_resume.md") -> tuple[ResumeMetadata, str]:
    """Parse the hybrid YAML/Markdown master resume."""
    resume_path = Path(path)
    if not resume_path.exists():
        raise FileNotFoundError(f"Master resume not found: {path}")
        
    with open(resume_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    if not content.startswith("---"):
        raise ValueError("Master resume must start with YAML frontmatter enclosed in '---'")
        
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Invalid frontmatter format in master resume.")
        
    yaml_content = parts[1]
    markdown_content = parts[2].strip()
    
    try:
        metadata_dict = yaml.safe_load(yaml_content)
        metadata = ResumeMetadata(**metadata_dict)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML frontmatter: {e}")
    except ValidationError as e:
        raise ValueError(f"Invalid master resume metadata schema: {e}")
        
    return metadata, markdown_content

class SafeResumeData(BaseModel):
    skills: dict[str, list[str]]
    preferences: dict
    experience: str

def get_safe_resume_data(path: str = "master_resume.md") -> SafeResumeData:
    """Extract skills taxonomy and experience bullets without PII."""
    metadata, content = parse_master_resume(path)
    
    return SafeResumeData(
        skills=metadata.skills,
        preferences=metadata.preferences,
        experience=content
    )
