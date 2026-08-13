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
