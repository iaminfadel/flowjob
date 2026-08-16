from enum import Enum
from typing import Optional, Literal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON
from pydantic import BaseModel

class FitScore(BaseModel):
    score: int
    matching_skills: list[str]
    missing_skills: list[str]
    recommendation: Literal["apply", "skip", "review"]

class JobState(str, Enum):
    NEW = "NEW"
    ANALYZED = "ANALYZED"
    SKIPPED = "SKIPPED"
    DRAFTED = "DRAFTED"
    EDITED = "EDITED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    TAILOR_FAIL = "TAILOR_FAIL"
    EDIT_FAIL = "EDIT_FAIL"
    REJECTED = "REJECTED"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    UNFIXABLE = "UNFIXABLE"

class Job(SQLModel, table=True):
    id: str = Field(primary_key=True)  # sha256(url + title + company)[:12]
    url: str
    title: str
    company: str
    location: str
    posted_date: str
    jd_text: str
    state: JobState = Field(default=JobState.NEW)
    tailor_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
    grilling_transcript: dict = Field(default_factory=dict, sa_column=Column(JSON))
    date_applied: Optional[str] = None
    cv_path: Optional[str] = None
    fit_score: Optional[int] = None
    edit_score: Optional[int] = None

class ErrorRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    agent_name: str
    error_type: str
    stack_trace: str
    job_id: str
    timestamp: str
    retry_count: int

class PipelineRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: str
    success: bool = True
