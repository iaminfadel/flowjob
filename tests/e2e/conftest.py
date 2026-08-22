"""pytest configuration for e2e tests: skip unless FLOWJOB_E2E=1 is set."""

import os
import pytest


def pytest_runtest_setup(item):
    if item.get_closest_marker("e2e") and not os.environ.get("FLOWJOB_E2E"):
        pytest.skip("set FLOWJOB_E2E=1 to run real-browser end-to-end tests")