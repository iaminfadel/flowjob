from playwright.sync_api import sync_playwright
import os

def login_linkedin():
    os.makedirs("browser_data", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="browser_data",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = browser.new_page()
        page.goto("https://www.linkedin.com/login")
        print("Please log in. Close the browser manually when done.")
        # Wait for the user to close the page
        page.wait_for_event("close", timeout=0)
        browser.close()

def check_session_health() -> bool:
    os.makedirs("browser_data", exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="browser_data",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        try:
            page = browser.pages[0] if browser.pages else browser.new_page()
            try:
                page.goto("https://www.linkedin.com/", wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass
            
            # Fail fast on CAPTCHAs
            captcha_challenge = page.get_by_role("heading", name="security check", exact=False)
            if captcha_challenge.is_visible():
                print("❌ Pipeline paused! CAPTCHA detected.")
                return False

            # Check for profile nav item or feed redirect
            try:
                # If logged in, LinkedIn typically redirects to /feed/
                page.wait_for_url("**/feed/**", timeout=5000)
                is_logged_in = True
            except Exception:
                try:
                    # Fallback to checking the "Me" nav item
                    profile_nav = page.get_by_text("Me", exact=True)
                    profile_nav.wait_for(timeout=5000)
                    is_logged_in = profile_nav.is_visible()
                except Exception:
                    is_logged_in = False
            
            if not is_logged_in:
                print("❌ Pipeline paused! LinkedIn session is invalid. Please run `flowjob login`.")
                
            return is_logged_in
        except Exception as e:
            print(f"❌ Pipeline paused! Session health probe failed: {e}")
            print("Please run `flowjob login` to renew session.")
            return False
        finally:
            browser.close()
