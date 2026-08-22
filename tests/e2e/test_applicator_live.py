"""Real-browser e2e: applicator modal loop pauses on dropdown questions.

Needs a live LinkedIn Easy Apply job URL in FLOWJOB_E2E_JOB_URL whose form
includes a dropdown question. Run:
    FLOWJOB_E2E=1 FLOWJOB_E2E_JOB_URL=<url> uv run pytest -m e2e tests/e2e/test_applicator_live.py

The test drives the real modal and asserts the pause path fires (wait_fn
called with the dropdown prompt) instead of guessing an answer.
"""

import os
import pytest

from src.browser.driver import get_browser_driver
from src.agents.applicator import ApplicatorAgent


@pytest.mark.e2e
def test_applicator_pauses_on_dropdown_question():
    job_url = os.environ.get("FLOWJOB_E2E_JOB_URL")
    if not job_url:
        pytest.skip("set FLOWJOB_E2E_JOB_URL to a live job with a dropdown question")

    driver = get_browser_driver()
    agent = ApplicatorAgent(driver=driver)
    prompts = []
    # wait_fn records the pause instead of blocking on stdin; the test ends at
    # the pause — that IS the assertion target.
    def wait_fn(prompt=""):
        prompts.append(prompt)
        raise KeyboardInterrupt  # end the modal loop after the pause fires

    class FakeJob:
        url = job_url
        title = "E2E dropdown probe"
        company = "live"

    try:
        agent.run(FakeJob(), wait_fn)
    except KeyboardInterrupt:
        pass

    assert any("dropdown" in p.lower() for p in prompts), (
        f"expected a dropdown pause prompt, got: {prompts}"
    )