import hashlib
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from src.db.models import JobPosting, JobState
from datetime import datetime

def generate_id(url: str, title: str, company: str) -> str:
    """Generate idempotency key."""
    raw = f"{url}{title}{company}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:12]

def clean_url(raw_url: str) -> str:
    """Strip query params from LinkedIn job URL."""
    parsed = urlparse(raw_url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def scrape_linkedin_jobs(search_url: str, max_jobs: int = 30, headless: bool = False, user_data_dir: str = "browser_data") -> list[JobPosting]:
    """Scrapes LinkedIn Easy Apply jobs using Playwright."""
    jobs = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = browser.new_page()
        page.goto(search_url)
        
        # Wait for job list to load
        try:
            page.wait_for_selector(".job-card-container", timeout=15000)
        except PlaywrightTimeout:
            print("No jobs found or timeout waiting for job list.")
            browser.close()
            return []
            
        # Give it a moment to stabilize
        time.sleep(2)
        
        job_cards = page.query_selector_all(".job-card-container")
        print(f"Found {len(job_cards)} job cards on the page.")
        
        for card in job_cards[:max_jobs]:
            try:
                # Scroll card into view and click
                card.scroll_into_view_if_needed()
                card.click()
                time.sleep(1.5) # Navigation noise
                
                # Wait for detail pane to update
                page.wait_for_selector(".job-details-jobs-unified-top-card__job-title", timeout=5000)
                
                # Extract basic info
                title_elem = page.query_selector(".job-details-jobs-unified-top-card__job-title")
                company_elem = page.query_selector(".job-details-jobs-unified-top-card__company-name")
                location_elem = page.query_selector(".job-details-jobs-unified-top-card__bullet")
                jd_elem = page.query_selector("#job-details")
                
                if not title_elem or not company_elem or not jd_elem:
                    continue
                    
                title = title_elem.inner_text().strip()
                company = company_elem.inner_text().strip()
                location = location_elem.inner_text().strip() if location_elem else "Unknown"
                jd_text = jd_elem.inner_text().strip()
                
                url_elem = page.query_selector(".job-details-jobs-unified-top-card__job-title a")
                raw_url = url_elem.get_attribute("href") if url_elem else page.url
                url = clean_url(raw_url)
                
                # Check for Easy Apply button
                apply_button = page.query_selector(".jobs-apply-button")
                if not apply_button:
                    print(f"Skipping {title} at {company}: No apply button found.")
                    continue
                    
                button_text = apply_button.inner_text().strip().lower()
                if "easy apply" not in button_text:
                    print(f"Skipping {title} at {company}: Found '{button_text}', not Easy Apply.")
                    continue
                    
                job_id = generate_id(url, title, company)
                
                job = JobPosting(
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
                print(f"Error scraping a job card: {e}")
                continue
                
        browser.close()
        
    return jobs
