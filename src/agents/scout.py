import hashlib
import time
from urllib.parse import urlparse
from typing import Optional
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from src.db.models import Job, JobState
from src.utils.display import display_env
from src.browser.driver import BrowserDriver, get_browser_driver
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

def scrape_linkedin_jobs(search_url: str, max_jobs: int = 30, headless: bool = False, user_data_dir: str = "browser_data", driver: Optional[BrowserDriver] = None) -> list[Job]:
    """Scrapes LinkedIn Easy Apply jobs using Playwright robust URL extraction."""
    driver = driver or get_browser_driver()
    jobs = []
    
    with driver.session(headless=headless) as page:
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
        
        # Collect job URLs by scrolling through search results
        print(f"Collecting job URLs (up to {max_jobs})...")
        job_urls = []
        no_new_jobs_count = 0
        max_scroll_cycles = 30
        
        # Initial settle
        time.sleep(2)
        
        for cycle in range(max_scroll_cycles):
            # 1. Query all job view links in current DOM
            elements = page.locator("a[href*='/jobs/view/']").all()
            new_found = 0
            for el in elements:
                try:
                    href = el.evaluate("el => el.href")
                    if href:
                        clean = clean_url(href)
                        if clean not in job_urls:
                            job_urls.append(clean)
                            new_found += 1
                except Exception:
                    pass
            
            if new_found > 0:
                no_new_jobs_count = 0
                print(f"Found {len(job_urls)} unique job URLs so far (added +{new_found})...")
            else:
                no_new_jobs_count += 1
            
            if len(job_urls) >= max_jobs:
                break
                
            # If no new jobs found after multiple scrolls, attempt pagination
            if no_new_jobs_count >= 3:
                if len(job_urls) < max_jobs:
                    next_button = page.locator(
                        "button[aria-label='Next'], button[aria-label*='next page' i], button.artdeco-pagination__button--next, [data-test-pagination-page-btn].active + li button"
                    ).first
                    try:
                        if next_button.is_visible() and next_button.is_enabled():
                            print("Reached end of current page, clicking Next page...")
                            next_button.click()
                            time.sleep(2.5)
                            no_new_jobs_count = 0
                            continue
                    except Exception:
                        pass
                # No more jobs or pagination available
                break
            
            # Scroll both list containers and window to trigger lazy rendering
            page.evaluate("""(() => {
                const selectors = [
                    '.jobs-search-results-list',
                    '.scaffold-layout__list',
                    'div.jobs-search-results-list',
                    'div[data-view-name="job-search-results-list"]',
                    'ul.jobs-search__results-list',
                    '.jobs-search__left-rail',
                    'div.jobs-search-two-pane__wrapper'
                ];
                let scrolled = false;
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && (el.scrollHeight > el.clientHeight)) {
                        el.scrollBy(0, 600);
                        scrolled = true;
                    }
                }
                window.scrollBy(0, 600);
                return scrolled;
            })()""")
            time.sleep(1.5)
                    
        print(f"Found {len(job_urls)} unique job URLs. Will scrape up to {max_jobs}.")
        
        if not job_urls:
            print("No jobs found on search page after all attempts. Dumping DOM.")
            driver.capture_diagnostics(page, tag="debug_scout")
            return []
            
        # 2. Visit each job directly
        first_failure_dumped = False
        for url in job_urls[:max_jobs]:
            try:
                print(f"Navigating to job: {url}")
                try:
                    # Use 'commit' for HTTP (avoids long-poll hang) and 'domcontentloaded' for file:// URLs
                    wait_mode = "domcontentloaded" if url.startswith("file://") else "commit"
                    page.goto(url, wait_until=wait_mode, timeout=30000)
                except PlaywrightTimeout:
                    print("⚠️ Job detail navigation timed out, proceeding with DOM...")

                # Give the already-rendered page a moment to settle its JS
                time.sleep(1.5 if url.startswith("file://") else 3)
                
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
                
                # ── JD Extraction ─────────────────────────────────────────────
                # LinkedIn lazy-renders #job-details only after the element is
                # scrolled into view. Scroll down first to trigger it, then try
                # the specific container; fall back to main (always populated).
                try:
                    page.evaluate("window.scrollBy(0, 600)")
                    time.sleep(1)
                except Exception:
                    pass

                jd_text = ""

                # Try #job-details via page.evaluate — instant null if absent,
                # no wait_for_selector timeout (the earlier hang source).
                for jd_selector in ["#job-details", ".jobs-description__content", "article"]:
                    try:
                        raw = page.evaluate(
                            f"""(() => {{
                                const el = document.querySelector({repr(jd_selector)});
                                return el ? el.innerText : null;
                            }})()"""
                        )
                        if raw and len(raw.strip()) > 20:
                            jd_text = raw.strip()
                            break
                    except Exception:
                        continue

                # main is always populated on LinkedIn job pages
                if not jd_text:
                    try:
                        jd_text = page.locator("main").first.inner_text().strip()
                    except Exception:
                        jd_text = ""

                # ── Post-extraction cleaning ──────────────────────────────────
                # LinkedIn pages include a lot of UI chrome (Premium upsells,
                # applicant counts, navigation) before and after the real JD.
                # Slice from "About the job" heading if present.
                if jd_text:
                    lower = jd_text.lower()
                    about_idx = lower.find("about the job")
                    if about_idx != -1:
                        # Keep everything from "About the job" onward
                        jd_text = jd_text[about_idx + len("about the job"):].lstrip("\n ").strip()

                    # Truncate at known LinkedIn UI noise that follows the JD.
                    # Guard: only truncate if marker appears after the first 300 chars
                    # so phrases like "Show more" embedded in the real JD body are kept.
                    _noise_markers = [
                        "Similar jobs",
                        "People also viewed",
                        "You may also know",
                        "Get AI-powered advice",
                        "Try Premium",
                        "See who LinkedIn",
                        "People you can reach",
                        "Meet the hiring team",
                        "Show more",
                        "Show less",
                    ]
                    for marker in _noise_markers:
                        idx = jd_text.find(marker)
                        if idx != -1 and idx > 300:
                            jd_text = jd_text[:idx].strip()
                            break
                
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
                
    return jobs
