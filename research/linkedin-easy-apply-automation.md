# Research: LinkedIn Easy Apply Form Anatomy & Playwright Automation

> Resolves [#3](https://github.com/iaminfadel/flowjob/issues/3)

## Sources

- Web research on LinkedIn Easy Apply automation patterns (2024–2026)
- Playwright documentation patterns

## LinkedIn Easy Apply Form Structure

### Multi-Step Modal
The Easy Apply flow is a **React-based multi-step modal** that appears as an overlay:

1. **Step 1: Contact Info** — pre-filled from LinkedIn profile (name, email, phone, location)
2. **Step 2: Resume** — file upload widget for PDF/DOCX. May show "use last uploaded" option.
3. **Step 3: Screening Questions** — variable. Common types:
   - Text inputs (years of experience, salary expectations)
   - Radio buttons (authorization to work, willing to relocate)
   - Dropdowns (education level, proficiency in X)
   - Checkboxes (acknowledge terms)
4. **Step 4: Review** — summary of all fields before submission
5. **Submit** — final button

Not every listing uses all steps — some Easy Apply jobs skip screening questions entirely.

### DOM & Selectors

**Critical insight**: LinkedIn's class names are obfuscated and change frequently. Static CSS selectors break constantly.

**Recommended approach — Playwright Locator API:**
```python
# ✅ Resilient selectors
page.get_by_role("button", name="Easy Apply")
page.get_by_role("button", name="Next")
page.get_by_role("button", name="Review")
page.get_by_role("button", name="Submit application")
page.get_by_label("Years of Experience")
page.get_by_label("Upload resume")

# ❌ Fragile selectors — avoid
page.query_selector(".job-card-container")
page.query_selector(".artdeco-modal")
```

### Resume Upload
- The file upload is an `<input type="file">` element, possibly hidden behind a styled button.
- Playwright's `input_file.set_input_files(path)` handles this.
- Some listings show a "Use your last uploaded resume" option — the agent must ensure it uploads the freshly tailored one, not the cached default.

## Anti-Automation Measures

1. **Behavioral detection** — monitors mouse movement patterns, typing speed, click cadence. Inhuman patterns trigger flags.
2. **Rate limiting** — applying to too many jobs too quickly triggers temporary blocks or CAPTCHAs.
3. **Headless detection** — LinkedIn checks for automation signals (`navigator.webdriver`, `window.chrome`, etc.).
4. **Session validation** — tokens expire; stale sessions get 401s.

### Mitigation Strategies

| Measure | Mitigation |
|---------|-----------|
| Behavioral detection | Randomized delays (1.2–3.4s between actions), slow scrolling, realistic mouse paths |
| Rate limiting | Hard cap of 10–20 applications/day, spread across hours |
| Headless detection | Run **headed** (non-headless), use `--disable-blink-features=AutomationControlled` |
| Session expiry | Persistent browser profile via `storageState`, re-auth when expired |

### Playwright Configuration

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch_persistent_context(
        user_data_dir="./browser_data",
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ..."
    )
    page = browser.pages[0] if browser.pages else await browser.new_page()
```

### Authentication

Using `launch_persistent_context` with a `user_data_dir`:
1. First run: user logs in manually in the browser window
2. Subsequent runs: session cookies persist in the user data directory
3. When session expires: the agent detects a login page and alerts the user

This is equivalent to Playwright's `storageState` but more robust — it preserves the entire browser profile, not just cookies/localStorage.

## Scraping Job Listings

### LinkedIn Job Search URL Pattern
```
https://www.linkedin.com/jobs/search/?keywords={query}&location={location}&f_TPR=r86400&f_AL=true&sortBy=DD
```

Parameters:
- `f_TPR=r86400` — posted in last 24 hours
- `f_AL=true` — Easy Apply only
- `sortBy=DD` — sort by date (most recent first)

### Extracting Job Data
- Job cards are in a scrollable list panel
- Each card has: title, company, location, posted date, Easy Apply badge
- Clicking a card loads the full JD in the right panel
- JD text is in a `<div>` with description content — extract via `element.inner_text()`

## Common Failure Modes

1. **LinkedIn UI update** — selectors break. Expect 2–4 updates/year.
2. **CAPTCHA challenge** — requires human intervention. Agent should pause and notify.
3. **Account restriction** — too many applications triggers a cooldown period (usually 24h).
4. **Screening question the agent can't answer** — novel question types. Agent should skip or flag.
5. **Network/timeout** — standard retry logic.

## Recommendations for FlowJob

1. **Run headed, not headless** — reduces detection risk dramatically.
2. **Use Playwright Locator API exclusively** — role-based and label-based selectors are resilient to DOM changes.
3. **Implement a "generic form handler"** — identify field types by `<label>` text and map to stored answers from config.
4. **Hard cap at 15 apps/day** — balance between speed and safety.
5. **Random delays of 2–5 seconds** between every interaction, plus longer pauses (30–60s) between applications.
6. **Dry-run mode** — fill everything but don't click Submit. Essential for testing.
