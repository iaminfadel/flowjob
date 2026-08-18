"""Data models for the Grilling Session transcript lifecycle."""

from enum import Enum
from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field


class GapStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    DROPPED = "dropped"


class TurnRecord(BaseModel):
    role: Literal["interviewer", "candidate", "system"]
    text: str
    timestamp: Optional[str] = None


class GapRecord(BaseModel):
    requirement: str
    must_have: bool = True
    status: GapStatus = GapStatus.PENDING
    turns: List[TurnRecord] = Field(default_factory=list)
    synthesized_bullet: Optional[str] = None
    note: str = ""


class GrillingTranscript(BaseModel):
    active_requirement: Optional[str] = None
    gaps: Dict[str, GapRecord] = Field(default_factory=dict)
