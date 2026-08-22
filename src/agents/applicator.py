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

    @staticmethod
    def _visible_button(page, names: list[str]):
        """First visible button matching any accessible name.

        LinkedIn's aria-labels override inner text for accessible naming
        (e.g. 'Next' has aria-label 'Continue to next step'), so the
        exact aria-label must be matched, with the inner text as fallback.
        """
        for name in names:
            loc = page.get_by_role("button", name=name, exact=True).first
            if loc.is_visible():
                return loc
        return None

    def _modal_loop(self, page, wait_fn) -> bool:
        """Drive the Easy Apply modal; blocks via wait_fn on unknown-form-field pauses."""
        while True:
            # LinkedIn renders these as <button> or <a> depending on variant;
            # aria-labels: 'Continue to next step' / 'Review your application' /
            # 'Submit application'
            next_btn = self._visible_button(page, ["Continue to next step", "Next"])
            review_btn = self._visible_button(page, ["Review your application", "Review"])
            submit_btn = self._visible_button(page, ["Submit application"])

            if submit_btn:
                print("[Applicator] Found 'Submit application' button. Submitting...")
                self._random_sleep(1.0, 3.0)
                submit_btn.click()
                self._random_sleep(3.0, 5.0)
                print("[Applicator] Application submitted successfully.")
                return True

            if next_btn or review_btn:
                before = page.get_by_role("dialog").first.inner_text()
                btn_to_click = next_btn or review_btn
                btn_to_click.click()

                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except TimeoutError:
                    pass
                self._random_sleep(1.0, 2.0)

                # Unanswered additional questions render as visible <select>
                # dropdowns in the modal — pause for human input, never guess.
                selects = page.get_by_role("dialog").first.locator("select").all()
                if any(s.is_visible() for s in selects):
                    print("[Applicator] Additional question with dropdown detected.")
                    diag = self.driver.capture_diagnostics(page, tag="unknown_field")
                    print(f"[Applicator] Screenshot saved to {diag.get('screenshot')}")
                    print("\n[Applicator] PAUSED. Fill the dropdown(s) in the browser and click Next/Review...")
                    wait_fn("Press Enter once you have filled the dropdown(s) and clicked Next/Review... ")
                    self._random_sleep(1.0, 2.0)
                    continue

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

                # If the dialog did not advance, we are stuck on a question —
                # pause instead of re-clicking Next in a loop.
                after = page.get_by_role("dialog").first.inner_text()
                if before == after:
                    print("[Applicator] Step did not advance after clicking Next/Review.")
                    diag = self.driver.capture_diagnostics(page, tag="stuck_on_question")
                    print(f"[Applicator] Screenshot saved to {diag.get('screenshot')}")
                    print("\n[Applicator] PAUSED. Answer the question(s) in the browser and click Next/Review...")
                    wait_fn("The step did not advance — press Enter once you have answered and clicked Next/Review... ")
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
                
                # Find Easy Apply button (LinkedIn renders it as an <a> with
                # aria-label "Easy Apply to this job", or a <button>)
                easy_apply_btn = (
                    page.get_by_role("button", name="Easy Apply", exact=True)
                    .or_(page.get_by_role("link", name="Easy Apply", exact=False))
                    .first
                )
                if not easy_apply_btn.is_visible():
                    print("[Applicator] 'Easy Apply' button not found. Aborting.")
                    diag = self.driver.capture_diagnostics(page, tag="no_easy_apply")
                    print(f"[Applicator] Screenshot saved to {diag.get('screenshot')}")
                    return False
                
                easy_apply_btn.click()
                self._random_sleep(2.0, 3.0)

                # On some variants the SPA ignores the synthetic click and the
                # modal never opens — fall back to the anchor's apply URL.
                if page.get_by_role("dialog").count() == 0:
                    apply_href = easy_apply_btn.get_attribute("href")
                    if apply_href:
                        print("[Applicator] Modal did not open on click; navigating to apply URL.")
                        page.goto(apply_href)
                        self._random_sleep(2.0, 3.0)

                return self._modal_loop(page, wait_fn or input)
        except Exception as e:
            if str(e) == "CAPTCHA_DETECTED":
                raise
            print(f"[Applicator] Error during automation: {e}")
            return False

