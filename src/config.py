import yaml
from pathlib import Path
from pydantic import BaseModel, Field

class ScoutConfig(BaseModel):
    search_queries: list[str]
    max_scrape_per_run: int = 30

class AnalystConfig(BaseModel):
    min_fit_score: int = 70

class EditorConfig(BaseModel):
    min_keyword_coverage: int = 75

class ApplicatorConfig(BaseModel):
    max_apps_per_day: int = 10
    max_apps_per_hour: int = 1
    dry_run: bool = False
    require_approval: bool = True

class LLMConfig(BaseModel):
    llm_timeout_seconds: int = 60
    max_retries: int = 3

class DataConfig(BaseModel):
    data_retention_days: int = 90
    db_path: str = "flowjob.db"
    output_dir: str = "output/"
    browser_data_dir: str = "browser_data/"

class FlowJobConfig(BaseModel):
    scout: ScoutConfig
    analyst: AnalystConfig
    editor: EditorConfig
    applicator: ApplicatorConfig
    llm: LLMConfig
    data: DataConfig

def load_config(path: str = "flowjob.yaml") -> FlowJobConfig:
    """Load and validate the flowjob.yaml configuration file."""
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
        
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
        
    return FlowJobConfig(**data)
