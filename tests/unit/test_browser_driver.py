import pytest
from src.browser.driver import MockBrowserDriver, set_browser_driver, get_browser_driver


def test_mock_browser_driver():
    driver = MockBrowserDriver(is_healthy=True)
    assert driver.check_health() is True

    with driver.session() as page:
        assert page.url == "https://www.linkedin.com/feed/"
        page.goto("https://www.linkedin.com/jobs/view/123")
        assert page.url == "https://www.linkedin.com/jobs/view/123"

    diag = driver.capture_diagnostics(page, tag="test_tag", job_id="job999")
    assert "screenshot" in diag
    assert "dom" in diag
    assert len(driver.diagnostics) == 1
    assert driver.diagnostics[0]["tag"] == "test_tag"
