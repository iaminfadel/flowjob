import os
import random
import time
from typing import Callable, Optional
from playwright.sync_api import TimeoutError
from src.agents.runner import AgentRunner
from src.browser.driver import BrowserDriver, get_browser_driver

class ApplicatorAgent(AgentRunner):
    """
    Automates the Easy Apply flow on LinkedIn.
    Uses headed Playwright with persistent state to avoid anti-bot detection.
    Pauses and prompts the user via CLI for unknown form fields.
    """
    def __init__(self, client=None, driver: Optional[BrowserDriver] = None):
        super().__init__(client=client)
        self.driver = driver or get_browser_driver()

    def _random_sleep(self, min_s: float, max_s: float):
        time.sleep(random.uniform(min_s, max_s))

    def _modal_loop(self, page, wait_fn) -> bool:
        """Drive the Easy Apply modal; blocks via wait_fn on unknown-form-field pauses."""
        browser_data_dir = getattr(self.driver, "user_data_dir", "browser_data")
        while True:
            # Look for Next, Review, or Submit buttons
            next_btn = page.get_by_role("button", name="Next", exact=True).first
            review_btn = page.get_by_role("button", name="Review", exact=True).first
            submit_btn = page.get_by_role("button", name="Submit application", exact=True).first
            
            if submit_btn.is_visible():
                print("[Applicator] Found 'Submit application' button. Submitting...")
                self._random_sleep(1.0, 3.0)
                submit_btn.click()
                self._random_sleep(3.0, 5.0)
                print("[Applicator] Application submitted successfully.")
                return True
            
            if next_btn.is_visible() or review_btn.is_visible():
                btn_to_click = next_btn if next_btn.is_visible() else review_btn
                btn_to_click.click()
                
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except TimeoutError:
                    pass
                self._random_sleep(1.0, 2.0)
                
                # Check for error alerts
                error_alert = page.get_by_role("alert").first
                if error_alert.is_visible():
                    print("[Applicator] Form error detected (missing field).")
                    diag = self.driver.capture_diagnostics(page, tag="unknown_field")
                    screenshot_path = diag.get("screenshot", "unknown_field.png")
                    print(f"[Applicator] Screenshot saved to {screenshot_path}")
                    
                    # Block and wait for human input
                    print("\n[Applicator] PAUSED. Unknown field encountered.")
                    print("Please check the browser window or screenshot, fill the field manually, and click Next/Review... ")
                    wait_fn("Press Enter once you have filled the field and clicked Next/Review... ")
                    # Wait for transition
                    self._random_sleep(1.0, 2.0)
                continue
            
            # If we reach here, we are stuck or done
            print("[Applicator] No Next/Review/Submit buttons found. Check if application completed.")
            diag = self.driver.capture_diagnostics(page, tag="stuck")
            screenshot_path = diag.get("screenshot", "stuck.png")
            print(f"[Applicator] Stuck. Screenshot saved to {screenshot_path}. Aborting.")
            return False

    def run(self, job, wait_fn: Callable[[str], None] | None = None) -> bool:
        print(f"\n[Applicator] Starting automation for {job.title} at {job.company}")
        print("[Applicator] Opening browser...")
        
        try:
            with self.driver.session(headless=False) as page:
                # Add jitter before navigation
                self._random_sleep(1.0, 3.0)
                page.goto(job.url)
                
                # Scroll to simulate human reading
                self._random_sleep(2.0, 4.0)
                page.evaluate("window.scrollBy(0, 500)")
                self._random_sleep(1.0, 2.0)
                
                # Check for CAPTCHA or Login redirect
                if "login" in page.url.lower() or "challenge" in page.url.lower():
                    print("[Applicator] Redirected to login or CAPTCHA. Aborting automation.")
                    raise RuntimeError("CAPTCHA_DETECTED")
                
                # Find Easy Apply button
                easy_apply_btn = page.get_by_role("button", name="Easy Apply", exact=True).first
                if not easy_apply_btn.is_visible():
                    print("[Applicator] 'Easy Apply' button not found. Aborting.")
                    return False
                
                easy_apply_btn.click()
                self._random_sleep(1.0, 2.0)
                
                return self._modal_loop(page, wait_fn or input)
        except Exception as e:
            if str(e) == "CAPTCHA_DETECTED":
                raise
            print(f"[Applicator] Error during automation: {e}")
            return False

