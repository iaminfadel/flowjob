"""Deep BrowserDriver module providing unified Playwright persistent context management,
anti-bot evasions, stale lock recovery, and diagnostic screenshot capture.
"""

from __future__ import annotations

import os
import random
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generator, Optional

from src.utils.display import display_env


class BrowserDriver(ABC):
    """Abstract deep interface for browser automation and session management."""

    @abstractmethod
    def login_interactive(self) -> None:
        """Launch headed interactive browser for manual login."""
        pass

    @abstractmethod
    def check_health(self) -> bool:
        """Check if LinkedIn session is active and healthy (no login redirect / CAPTCHA)."""
        pass

    @abstractmethod
    @contextmanager
    def session(self, headless: bool = False) -> Generator[Any, None, None]:
        """Context manager providing an active Page instance inside a persistent browser context."""
        pass

    @abstractmethod
    def capture_diagnostics(self, page: Any, tag: str, job_id: Optional[str] = None) -> dict[str, str]:
        """Capture screenshot and DOM dump on error or unexpected state."""
        pass

    def random_sleep(self, min_s: float = 1.0, max_s: float = 3.0):
        """Add jitter to emulate human delays."""
        time.sleep(random.uniform(min_s, max_s))


class PlaywrightBrowserDriver(BrowserDriver):
    """Production Playwright persistent context driver with anti-bot defenses."""

    def __init__(self, user_data_dir: str = "browser_data", diagnostics_dir: str = "data"):
        self.user_data_dir = user_data_dir
        self.diagnostics_dir = diagnostics_dir

    def _cleanup_stale_locks(self):
        """Remove stale Chromium SingletonLock files from dead processes."""
        lock_file = os.path.join(self.user_data_dir, "SingletonLock")
        if os.path.islink(lock_file) or os.path.exists(lock_file):
            try:
                target = os.readlink(lock_file) if os.path.islink(lock_file) else ""
                if "-" in target:
                    pid_str = target.split("-")[-1]
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        try:
                            os.kill(pid, 0)
                        except OSError:
                            # Process does not exist; lock is stale
                            os.unlink(lock_file)
                            for extra in ("SingletonCookie", "SingletonSocket"):
                                p = os.path.join(self.user_data_dir, extra)
                                if os.path.exists(p) or os.path.islink(p):
                                    try:
                                        os.unlink(p)
                                    except Exception:
                                        pass
            except Exception:
                pass

    def login_interactive(self) -> None:
        os.makedirs(self.user_data_dir, exist_ok=True)
        self._cleanup_stale_locks()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=False,
                env=display_env(),
                args=["--disable-blink-features=AutomationControlled", "--disable-gpu"],
                viewport={"width": 1280, "height": 720},
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto("https://www.linkedin.com/login")
            print("Please log in to LinkedIn in the browser window. Waiting for navigation to feed...")
            try:
                page.wait_for_url("https://www.linkedin.com/feed/**", timeout=300000)
                print("Login successful! State saved to browser_data.")
            except Exception:
                print("Login timed out or was not completed.")
            finally:
                browser.close()

    def check_health(self) -> bool:
        os.makedirs(self.user_data_dir, exist_ok=True)
        self._cleanup_stale_locks()
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=False,
                    env=display_env(),
                    args=["--disable-blink-features=AutomationControlled", "--disable-gpu"],
                    viewport={"width": 1280, "height": 720},
                )
                page = browser.pages[0] if browser.pages else browser.new_page()
                try:
                    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=45000)
                except PlaywrightTimeout:
                    pass

                time.sleep(2)
                current_url = page.url.lower()

                if "login" in current_url or "checkpoint" in current_url or "challenge" in current_url:
                    browser.close()
                    return False

                if page.locator(".feed-identity-module").count() > 0 or "feed" in current_url:
                    browser.close()
                    return True

                browser.close()
                return False
        except Exception as e:
            print(f"[BrowserDriver] Health check error: {e}")
            return False

    @contextmanager
    def session(self, headless: bool = False) -> Generator[Any, None, None]:
        os.makedirs(self.user_data_dir, exist_ok=True)
        self._cleanup_stale_locks()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=headless,
                env=display_env(),
                args=["--disable-blink-features=AutomationControlled", "--disable-gpu"],
                viewport={"width": 1280, "height": 720},
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                yield page
            finally:
                try:
                    context.close()
                except Exception:
                    pass

    def capture_diagnostics(self, page: Any, tag: str, job_id: Optional[str] = None) -> dict[str, str]:
        os.makedirs(self.diagnostics_dir, exist_ok=True)
        prefix = f"{job_id}_{tag}" if job_id else tag
        ts = int(time.time())
        screenshot_path = os.path.join(self.diagnostics_dir, f"{prefix}_{ts}.png")
        dom_path = os.path.join(self.diagnostics_dir, f"{prefix}_{ts}.html")

        results = {}
        try:
            if hasattr(page, "screenshot"):
                page.screenshot(path=screenshot_path)
                results["screenshot"] = screenshot_path
        except Exception:
            pass

        try:
            if hasattr(page, "content"):
                with open(dom_path, "w", encoding="utf-8") as f:
                    f.write(page.content())
                results["dom"] = dom_path
        except Exception:
            pass

        return results


class MockBrowserDriver(BrowserDriver):
    """Mock adapter for zero-overhead unit/integration testing without Chromium."""

    def __init__(self, is_healthy: bool = True, fake_page: Any = None):
        self.is_healthy = is_healthy
        self.fake_page = fake_page or _DefaultFakePage()
        self.diagnostics: list[dict] = []

    def login_interactive(self) -> None:
        pass

    def check_health(self) -> bool:
        return self.is_healthy

    @contextmanager
    def session(self, headless: bool = False) -> Generator[Any, None, None]:
        yield self.fake_page

    def capture_diagnostics(self, page: Any, tag: str, job_id: Optional[str] = None) -> dict[str, str]:
        diag = {"tag": tag, "job_id": job_id, "timestamp": time.time()}
        self.diagnostics.append(diag)
        return {"screenshot": f"mock://{tag}.png", "dom": f"mock://{tag}.html"}


class _DefaultFakePage:
    def __init__(self):
        self.url = "https://www.linkedin.com/feed/"

    def goto(self, url: str, **kwargs):
        self.url = url

    def evaluate(self, script: str):
        pass


_global_driver: Optional[BrowserDriver] = None


def get_browser_driver() -> BrowserDriver:
    global _global_driver
    if _global_driver is None:
        _global_driver = PlaywrightBrowserDriver()
    return _global_driver


def set_browser_driver(driver: BrowserDriver) -> None:
    global _global_driver
    _global_driver = driver
