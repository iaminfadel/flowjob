"""Browser display resolution for headed Playwright launches.

Supports two setups:
- Local/SSH -X: Chrome opens on the client's X server (DISPLAY set by sshd).
- Remote VNC: point FLOWJOB_DISPLAY at the VNC display (e.g. ":1").
"""
from __future__ import annotations

import os
from typing import Optional


def resolve_display() -> Optional[str]:
    """Display to open the browser UI on. FLOWJOB_DISPLAY wins over DISPLAY."""
    return os.environ.get("FLOWJOB_DISPLAY") or os.environ.get("DISPLAY") or None


def display_env() -> Optional[dict]:
    """Playwright env override that pins DISPLAY, or None to inherit the process env."""
    display = resolve_display()
    if not display:
        return None
    env = dict(os.environ)
    env["DISPLAY"] = display
    return env
