import hashlib
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from src.db.models import Job, JobState
from datetime import datetime

def generate_id(url: str, title: str, company: str) -> str:
    """Generate idempotency key."""
    raw = f"{url}{title}{company}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:12]

def clean_url(raw_url: str) -> str:
    """Strip query params from LinkedIn job URL."""
    parsed = urlparse(raw_url)
    if not parsed.scheme:
        return raw_url.split("?")[0]
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def scrape_linkedin_jobs(search_url: str, max_jobs: int = 30, headless: bool = False, user_data_dir: str = "browser_data") -> list[Job]:
    """Scrapes LinkedIn Easy Apply jobs using Playwright robust URL extraction."""
    jobs = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = browser.new_page()
        print(f"Scout navigating to search URL: {search_url}")
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeout:
            print("⚠️ Initial page navigation timed out waiting for full load, proceeding with DOM...")
        
        # Wait for the page to at least finish its initial load
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            pass
        
        # Active polling: scroll and wait for job links to appear.
        # LinkedIn's "AI-powered job search" loads results lazily via JS,
        # so we need to give it time and scroll to trigger rendering.
        print("Waiting for job results to render...")
        job_urls = []
        max_attempts = 6
        for attempt in range(max_attempts):
            time.sleep(3)
            
            # Try multiple selectors for job links
            elements = page.locator("a[href*='/jobs/view/']").all()
            
            for el in elements:
                try:
                    href = el.evaluate("el => el.href")
                    if href:
                        clean = clean_url(href)
                        if clean not in job_urls:
                            job_urls.append(clean)
                except Exception:
                    pass
            
            if job_urls:
                print(f"Attempt {attempt+1}: Found {len(job_urls)} job URLs so far.")
                break
            
            # Scroll down to trigger lazy loading
            print(f"Attempt {attempt+1}: No jobs yet, scrolling to trigger load...")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.evaluate("window.scrollTo(0, 0)")
                    
        print(f"Found {len(job_urls)} unique job URLs. Will scrape up to {max_jobs}.")
        
        if not job_urls:
            print("No jobs found on search page after all attempts. Dumping DOM.")
            import os
            os.makedirs("data", exist_ok=True)
            with open("data/debug_scout_dom.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            # Take a screenshot too for visual debugging
            try:
                page.screenshot(path="data/debug_scout_screenshot.png", full_page=True)
                print("Screenshot saved to data/debug_scout_screenshot.png")
            except Exception:
                pass
            browser.close()
            return []
            
        # 2. Visit each job directly
        first_failure_dumped = False
        for url in job_urls[:max_jobs]:
            try:
                print(f"Navigating to job: {url}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except PlaywrightTimeout:
                    print("⚠️ Job detail navigation timed out waiting for full load, proceeding with DOM...")
                
                # Wait for page to fully load instead of waiting for a specific element
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except PlaywrightTimeout:
                    pass
                time.sleep(2)
                
                # Extract Title & Company — page.title() is the most reliable (e.g. "R&D Engineer | Company | LinkedIn")
                title = "Unknown Title"
                company = "Unknown Company"
                
                page_title = page.title()
                if page_title and "|" in page_title:
                    parts = [p.strip() for p in page_title.split("|")]
                    if len(parts) >= 2 and parts[0].lower() not in ["jobs", "linkedin", "0 notifications", "notifications"]:
                        title = parts[0]
                        company = parts[1]
                        
                # Fallback Title extraction if page title was generic
                if title == "Unknown Title":
                    for title_selector in ["h1", ".top-card-layout__title", "h2", ".t-24"]:
                        elems = page.locator(title_selector).all()
                        for elem in elems:
                            try:
                                txt = elem.inner_text().strip()
                                if txt and txt.lower() not in ["jobs", "linkedin", "0 notifications", "notifications", "home", "messaging", "my network"]:
                                    title = txt
                                    break
                            except Exception:
                                continue
                        if title != "Unknown Title":
                            break
                
                # Fallback Company extraction
                if company == "Unknown Company":
                    company_elem = page.locator("a[href*='/company/']").first
                    try:
                        if company_elem.is_visible():
                            company = company_elem.inner_text().strip()
                    except Exception:
                        pass
                
                # Location — best effort
                location = "Unknown Location"
                for loc_selector in [".job-details-jobs-unified-top-card__bullet", ".tvm__text--neutral", ".topcard__flavor--bullet"]:
                    loc_elem = page.locator(loc_selector).first
                    try:
                        if loc_elem.is_visible():
                            location = loc_elem.inner_text().strip()
                            break
                    except Exception:
                        continue
                
                # Extract JD Text — try multiple containers
                jd_text = ""
                for jd_selector in ["#job-details", "article", ".jobs-description__container", ".description__text"]:
                    jd_elem = page.locator(jd_selector).first
                    try:
                        if jd_elem.is_visible():
                            jd_text = jd_elem.inner_text().strip()
                            if jd_text:
                                break
                    except Exception:
                        continue
                
                # Last resort for JD: grab all visible text from the page body
                if not jd_text:
                    jd_text = page.locator("main").first.inner_text().strip() if page.locator("main").count() > 0 else ""
                
                if not jd_text:
                    print(f"Skipping {title} at {company}: Could not find job description text.")
                    if not first_failure_dumped:
                        first_failure_dumped = True
                        import os
                        os.makedirs("data", exist_ok=True)
                        with open("data/debug_job_detail_dom.html", "w", encoding="utf-8") as f:
                            f.write(page.content())
                        print("Job detail DOM dumped to data/debug_job_detail_dom.html")
                    continue
                    
                # Check for Easy Apply
                easy_apply_visible = False
                easy_apply_button = page.locator("button:has-text('Easy Apply')")
                try:
                    easy_apply_visible = easy_apply_button.first.is_visible()
                except Exception:
                    pass
                    
                if not easy_apply_visible:
                    # Fallback: check if the page text mentions Easy Apply anywhere
                    page_text = page.locator("body").inner_text()
                    if "easy apply" not in page_text.lower():
                        print(f"Skipping {title} at {company}: No Easy Apply found on details page.")
                        continue
                    
                job_id = generate_id(url, title, company)
                
                job = Job(
                    id=job_id,
                    url=url,
                    title=title,
                    company=company,
                    location=location,
                    posted_date=datetime.now().isoformat(),
                    jd_text=jd_text,
                    state=JobState.NEW
                )
                jobs.append(job)
                print(f"Scraped valid Easy Apply job: {title} at {company}")
                
            except Exception as e:
                print(f"Error scraping job {url}: {e}")
                continue
                
        browser.close()
        
    return jobs
