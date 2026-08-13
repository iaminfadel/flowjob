import yaml
from pathlib import Path
from pydantic import BaseModel, ValidationError

class ResumeMetadata(BaseModel):
    schema_version: str = "1"
    name: str
    title: str
    email: str
    phone: str
    location: str
    links: list[dict]
    skills: dict[str, list[str]]
    preferences: dict
    personal_nudge: dict
    education: list[dict]

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
    experience: str

def get_safe_resume_data(path: str = "master_resume.md") -> SafeResumeData:
    """Extract skills taxonomy and experience bullets without PII."""
    metadata, content = parse_master_resume(path)
    
    return SafeResumeData(
        skills=metadata.skills,
        experience=content
    )
