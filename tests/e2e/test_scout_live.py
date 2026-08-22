"""Real-browser end-to-end tests: scout against live LinkedIn.

Skipped by default; run with:
    FLOWJOB_E2E=1 uv run pytest -m e2e

These tests need a valid LinkedIn session (run `flowjob login` first) and
exercise the full browser-automation path. Failures here are real signals.
"""

import os
import pytest

from src.agents.scout import scrape_linkedin_jobs


@pytest.mark.e2e
def test_scout_fetches_real_jobs():
    """Scout returns at least one job from a real LinkedIn search URL."""
    url = (
        "https://www.linkedin.com/jobs/search/?keywords=software%20engineer"
        "&location=Worldwide&f_AL=true&f_TPR=r86400"
    )
    jobs = scrape_linkedin_jobs(url, max_jobs=5)
    assert len(jobs) > 0, f"Expected at least 1 job from {url}, got {len(jobs)}"
    for j in jobs:
        assert j.id
        assert j.title
        assert j.company
        assert j.url.startswith("https://www.linkedin.com/jobs/view/")