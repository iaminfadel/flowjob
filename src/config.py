import os
import yaml
from pathlib import Path
from pydantic import BaseModel, Field

class ScoutConfig(BaseModel):
    max_scrape_per_run: int = 30
    time_filter: str = "any"

class AnalystConfig(BaseModel):
    model: str = "google/gemini-2.5-pro"
    min_fit_score: int = 70

class TailorConfig(BaseModel):
    model: str = "google/gemini-2.5-pro"

class EditorConfig(BaseModel):
    model: str = "google/gemini-2.5-pro"
    min_keyword_coverage: int = 75

class CriticConfig(BaseModel):
    model: str = "google/gemini-2.5-pro"

class WriterConfig(BaseModel):
    model: str = "google/gemini-2.5-pro"
    max_writer_rounds: int = 3

class GrillingConfig(BaseModel):
    model: str = "google/gemini-2.5-pro"
    max_turns_per_gap: int = 5

class AuditorConfig(BaseModel):
    model: str = "google/gemini-2.5-pro"
    max_attempts: int = 3

class ApplicatorConfig(BaseModel):
    max_apps_per_day: int = 10
    max_apps_per_hour: int = 1
    dry_run: bool = False
    require_approval: bool = True

class LLMConfig(BaseModel):
    default_model: str = "google/gemini-2.5-pro"
    llm_timeout_seconds: int = 60
    max_retries: int = 3
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str | None = None

class DataConfig(BaseModel):
    data_retention_days: int = 90
    db_path: str = "flowjob.db"
    output_dir: str = "output/"
    browser_data_dir: str = "browser_data/"

class FlowJobConfig(BaseModel):
    scout: ScoutConfig = Field(default_factory=ScoutConfig)
    analyst: AnalystConfig = Field(default_factory=AnalystConfig)
    tailor: TailorConfig = Field(default_factory=TailorConfig)
    editor: EditorConfig = Field(default_factory=EditorConfig)
    critic: CriticConfig = Field(default_factory=CriticConfig)
    writer: WriterConfig = Field(default_factory=WriterConfig)
    grilling: GrillingConfig = Field(default_factory=GrillingConfig)
    auditor: AuditorConfig = Field(default_factory=AuditorConfig)
    applicator: ApplicatorConfig = Field(default_factory=ApplicatorConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    data: DataConfig = Field(default_factory=DataConfig)

def load_config(path: str = "flowjob.yaml") -> FlowJobConfig:
    """Load and validate the flowjob.yaml configuration file."""
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v

    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
        
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
        
    config = FlowJobConfig(**data)

    if os.environ.get("OPENROUTER_API_KEY"):
        config.llm.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")

    override = os.environ.get("FLOWJOB_MODEL")
    if override:
        config.llm.default_model = override
        config.analyst.model = override
        config.tailor.model = override
        config.editor.model = override
        config.critic.model = override
        config.writer.model = override
        config.grilling.model = override
        config.auditor.model = override

    return config
