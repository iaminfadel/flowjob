"""Shared pipeline types: the cycle summary and session-health error.

Lives apart from the engine implementation so hosts (CLI, TUI) and tests can
import them without pulling in the full engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


class SessionHealthError(RuntimeError):
    """Raised when the browser session health probe fails inside an in-process host."""


@dataclass
class CycleSummaryResult:
    """Summary outcomes of a single pipeline cycle."""

    duration_s: float = 0.0
    jobs_scouted: int = 0
    jobs_analyzed: int = 0
    jobs_tailored: int = 0
    jobs_needs_evidence: int = 0
    jobs_unfixable: int = 0
    jobs_edited: int = 0
    jobs_applied: int = 0
    jobs_skipped: int = 0
    jobs_failed: int = 0
    halted_reason: Optional[str] = None
    counts_delta: Dict[str, int] = field(default_factory=dict)
