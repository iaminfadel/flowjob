# FlowJob: Agentic Job Application Pipeline
## Design Specification v1.1

FlowJob is an automated, multi-agent pipeline built on the Google Antigravity SDK. It discovers job postings, analyzes fit, generates tailored resumes, runs editorial QA, and stages applications for human approval.

> **v1.1 changes from v1.0**: Human approval gate added (C001), Checker Agent replaced with Editor Agent (C005), JobState machine added (C007), PII segmentation (C004), full error handling model (C008), and 11 additional mitigations from the concern register.

---

## 1. Architecture Overview

FlowJob uses a hybrid orchestration model: **deterministic Python code drives the pipeline; AGY SDK agents are specialized processors at each stage.** The orchestrator is fully recoverable from SQLite state — no in-memory state survives restarts.

### 1.1 Pipeline Topology

```
[Trigger / Watch Mode]
       │
       ▼
[Session Health Probe] ──FAIL──► [Halt + Notify User]
       │ PASS
       ▼
[Scout Agent]──────────────────────► [SQLite Job Queue]
       │ new jobs only (deduped)
       ▼
[Analyst Agent]
       │ fit_score < threshold
       │──────────────────────────► DROP (state = skipped)
       │ fit_score ≥ threshold
       ▼
[Tailor Agent]
       │
       ▼
[Editor Agent] ◄──────────────── feedback loop (max 1 retry)
       │ pass
       ▼
[PDF Generator] (Playwright print-to-PDF + text extraction test)
       │
       ▼
[Human Approval Gate] ◄─── notify user via CLI / dashboard
       │ APPROVED
       ▼
[Applicator Agent]
  ├─ known fields   ──► auto-fill
  └─ unknown fields ──► pause + screenshot ──► user input ──► resume
       │
       ▼
[Logger] → SQLite ApplicationRecord
```

### 1.2 Watch Mode
FlowJob uses the AGY SDK `every(seconds, callback)` trigger with **temporal jitter** (45–90 min, non-uniform distribution — never fixed cadence). Before every wake-up cycle, it runs a Session Health Probe.

### 1.3 Modes of Operation

| Mode | Description |
|------|-------------|
| `flowjob watch` | Long-running watch mode with polling trigger |
| `flowjob run` | One-shot pipeline run |
| `flowjob run --url <url>` | Resume-only mode: skip Scout, process a user-supplied job URL |
| `flowjob run --dry-run` | Full pipeline, no click/submit. Saves PDF + form answers to disk for inspection |
| `flowjob validate` | Parse `master_resume.md`, verify YAML schema, check bracket tags, warn on empty sections |
| `flowjob status` | Query SQLite and print application summary table |

---

## 2. Data Model

### 2.1 Master Resume
The user's single source of truth. Uses a hybrid format:
- **YAML Frontmatter**: Contact metadata, skills taxonomy, preferences (target roles, optional salary), **personal nudge** (tone/flavor for AI summary generation).
- **Markdown Body**: Exhaustive experience bullets tagged with `[brackets]` for semantic filtering.

**Schema version** must be declared in frontmatter (`schema_version: "1"`) so future format changes can be detected.

The Tailor Agent receives **only experience bullets and JD text** — never full contact information (C004 PII segmentation). Contact info is injected locally during PDF generation.

### 2.2 Pydantic Schemas

```python
class JobPosting(BaseModel):
    id: str                   # sha256(url + title + company)[:12] — idempotency key
    url: str
    title: str
    company: str
    location: str
    posted_date: str
    jd_text: str
    state: JobState           # see state machine below

class FitScore(BaseModel):
    score: int                # 0-100
    matching_skills: list[str]
    missing_skills: list[str]
    recommendation: Literal["apply", "skip", "review"]

class EditScore(BaseModel):
    keyword_coverage: int     # 0-100: JD keywords present in CV
    tone_flags: list[str]     # e.g. ["generic summary", "passive voice"]
    hallucination_flags: list[str]  # skills/years not in Master Resume
    format_flags: list[str]   # e.g. ["table detected", "image in content"]
    overall_pass: bool
    feedback: str             # detailed notes for Tailor Agent

class ApplicationRecord(BaseModel):
    id: str
    company: str
    role: str
    job_url: str
    state: JobState
    date_first_seen: str
    date_applied: str | None
    cv_path: str | None
    fit_score: int | None
    edit_score: int | None
    error_log: str | None

class ErrorRecord(BaseModel):
    agent_name: str
    error_type: str
    stack_trace: str
    job_id: str
    timestamp: str
    retry_count: int
```

### 2.3 JobState Machine

```
NEW → ANALYZED → DRAFTED → EDITED → PENDING_APPROVAL → APPLIED
 │        │          │         │             │               │
 │        └──SKIPPED │         └──EDIT_FAIL  └──REJECTED     │
 │                   └──TAILOR_FAIL                          │
 └─────────────────────────────────────────────── FAILED (dead-letter)
```

The orchestrator queries SQLite state on every wake-up. All transitions are persisted atomically — no in-memory state.

**Idempotency key**: `sha256(job_url + company + title)[:12]`. Duplicate postings are detected before processing.

---

## 3. Agent Specifications

Each agent has its own `LocalAgentConfig`, system prompt, and custom tools. Agent invocation is abstracted behind an `AgentRunner` interface so individual agents can be swapped to direct LLM calls if the SDK changes (C015).

### 3.1 Scout Agent
- **Role**: Discover new job postings from LinkedIn.
- **Tools**: `scrape_linkedin_jobs(search_url: str) -> list[JobPosting]`
- **Implementation**: Playwright with persistent `storageState` (headed, non-headless). LinkedIn search URL filters: `f_TPR=r86400` (last 24h), `f_AL=true` (Easy Apply), `sortBy=DD`.
- **Over-scrape buffer**: Collect up to 3× daily application cap. Maintain a backlog in SQLite so temporary blocks don't kill workflow.
- **Output**: `list[JobPosting]` (deduplicated against SQLite by idempotency key).

### 3.2 Analyst Agent
- **Role**: Score job fit against Master Resume and preferences config.
- **Tools**: None (pure LLM reasoning). Receives JD text + skills taxonomy from Master Resume (not full PII).
- **Output**: `FitScore`. Jobs below configured threshold transition to `SKIPPED`.

### 3.3 Tailor Agent
- **Role**: The creative brain. Selects relevant bullets from Master Resume and writes a custom summary using `personal_nudge`.
- **Tools**: `generate_cv_html(data, template) -> str`
- **PII boundary**: Contact info is NOT passed to this agent. It generates the narrative content only. Contact fields are injected during PDF generation.
- **Output**: CV HTML string.

### 3.4 Editor Agent *(replaces Checker Agent)*
- **Role**: Quality gate, not ATS oracle. Validates the CV against verifiable criteria.
- **Tools**: `score_cv_quality(cv_html: str, jd_text: str, master_resume: dict) -> EditScore`
- **What it checks**:
  - **Keyword coverage**: are JD terms present in the CV narrative?
  - **Fact-checking**: are claimed skills/years provable from Master Resume? Flag hallucinations.
  - **Tone audit**: generic AI-sounding phrases ("results-driven professional"), passive voice, filler words.
  - **Format flags**: tables, multi-column content, images, non-standard headings.
  - **Grammar & consistency**: tense consistency, date format consistency, Oxford comma.
  - **PDF parseability**: selectable text, no image-based content.
- **Iteration**: If first-pass fails, Tailor receives specific `EditScore.feedback` and tries once. Max 1 retry (2 LLM calls total per job). Token spend tracked in SQLite.
- **NOT what it does**: Does not simulate Workday/Greenhouse/Taleo. No fake ATS score.

### 3.5 Applicator Agent
- **Role**: Submit the application via browser automation. **Requires explicit human approval before executing.**
- **Scope v1**: LinkedIn Easy Apply only.
- **Tools**: `submit_easy_apply(job_url: str, cv_pdf_path: str, answers: dict) -> ApplicationResult`
- **Human approval gate** (C001): Application is staged in `PENDING_APPROVAL` state. Orchestrator notifies user via CLI. Agent only executes after explicit confirmation.
- **Known field map**: Hardcoded handler for common fields: name, email, phone, resume upload, cover letter.
- **Unknown field handling**: On unrecognized question — **stop, screenshot, pause pipeline, notify user**. Never guess. Answer is stored in `form_signature_log` per company for future reuse.
- **Navigation noise** (C002): Scroll JD 15–30s before applying, occasionally visit company page, randomized click paths, 2–5s micro-pauses.
- **Session health probe**: Before every run, verify search results load and account is not shadowbanned.
- **Circuit breaker**: On CAPTCHA, challenge screen, or unusual redirect — halt pipeline, notify user. Do not retry blindly.

---

## 4. LinkedIn Anti-Detection Architecture (C002)

| Risk | Mitigation |
|------|-----------|
| Fixed polling cadence | Temporal jitter: 45–90 min uniform random distribution |
| Headless browser detection | Run headed; `--disable-blink-features=AutomationControlled`; stealth plugins |
| Behavioral pattern detection | Navigation noise: scroll, visit company page, vary click paths, micro-pauses |
| TLS/JA3 fingerprinting | Run from residential IP — cloud VPS IPs are flagged |
| CAPTCHA / challenge | Circuit breaker: halt immediately, notify user, do not retry |
| Session expiry | Persistent browser context (`launch_persistent_context`); health probe before each cycle |
| Rate detection | Max 1 app/hour target (~8–10/day); hard stop at daily cap; never queue for next day automatically |

---

## 5. PII Segmentation Model (C004)

| Data | Sent to LLM? | Storage |
|------|-------------|---------|
| Name, email, phone | ❌ No | Injected at PDF generation time |
| Experience bullets | ✅ Yes | LLM context (ephemeral) |
| Skills taxonomy | ✅ Yes | LLM context (ephemeral) |
| JD text | ✅ Yes | SQLite (truncated to 10k chars) |
| Generated CV HTML | ✅ Yes (Editor) | Disk — purged per retention policy |
| Application records | ❌ Never LLM | SQLite only |

**Retention policy** (`data_retention_days` in `flowjob.yaml`): auto-purge old application records and generated CVs after N days.

---

## 6. Error Handling & Observability (C008)

### Retry Policy
- **Transient failures** (network, LLM rate limit): exponential backoff, max 3 retries.
- **Persistent failures**: Job transitions to `FAILED` (dead-letter). Logged as `ErrorRecord`. Never silently dropped.
- **LLM timeout**: All agent calls have a configured timeout (`llm_timeout_seconds` in YAML). Hanging calls abort and trigger retry.

### Dead-Letter Queue
Failed jobs after max retries go to a manual review state in SQLite. `flowjob status --failed` lists them with error types and stack traces.

### Logging
- `ErrorRecord` written to SQLite for every caught exception.
- Python `logging` module for structured runtime logs.
- AGY SDK `post_tool_call` hook for audit trail of every agent action.

---

## 7. Graceful Degradation (C003)

If automation fails (CAPTCHA, ban, DOM change), the pipeline can still produce value:

**Manual Application Package**: For any job in `EDITED` or `PENDING_APPROVAL` state, the orchestrator outputs a directory:
```
output/<company>_<role>_<date>/
├── tailored_cv.pdf
├── jd.txt
└── suggested_answers.txt   ← answers to known screening questions
```
User can apply manually using these materials.

**Resume-Only Mode**: `flowjob run --url <url>` skips Scout, processes a user-supplied job URL.

---

## 8. Configuration

### `flowjob.yaml`
```yaml
scout:
  search_queries: ["software engineer Egypt remote", "backend engineer Cairo"]
  max_scrape_per_run: 30       # over-scrape buffer
  
analyst:
  min_fit_score: 70            # jobs below this are skipped

editor:
  min_keyword_coverage: 75     # trigger retry if below

applicator:
  max_apps_per_day: 10
  max_apps_per_hour: 1
  dry_run: false               # override with --dry-run flag
  require_approval: true       # ALWAYS true in v1

llm:
  llm_timeout_seconds: 60
  max_retries: 3

data:
  data_retention_days: 90
  db_path: "flowjob.db"
  output_dir: "output/"
  browser_data_dir: "browser_data/"
```

### `.env`
```
GEMINI_API_KEY=...
```

---

## 9. Project Structure

```
flowjob/
├── src/
│   ├── agents/
│   │   ├── runner.py         # AgentRunner interface (C015 abstraction)
│   │   ├── scout.py
│   │   ├── analyst.py
│   │   ├── tailor.py
│   │   ├── editor.py
│   │   └── applicator.py
│   ├── tools/
│   │   ├── browser.py        # Playwright helpers
│   │   ├── pdf.py            # HTML → PDF + text extraction test
│   │   └── form_handler.py   # Easy Apply form map + unknown field handler
│   ├── pipeline/
│   │   ├── orchestrator.py   # Main pipeline logic
│   │   ├── state.py          # JobState machine
│   │   └── approval.py       # Human approval gate
│   ├── db/
│   │   ├── models.py         # Pydantic schemas + SQLite schema
│   │   └── store.py          # DB access layer
│   └── cli.py                # CLI entrypoint
├── templates/
│   └── resume.html           # Vanilla CSS template (no Tailwind)
├── tests/
│   ├── unit/
│   └── integration/
│       └── fixtures/         # Cached JD HTML for regression tests
├── scripts/
│   └── setup.sh
├── master_resume.md           # The user's master resume (gitignored for PII)
├── flowjob.yaml
├── .env                       # gitignored
├── .gitignore
├── pyproject.toml             # uv-managed, pins AGY SDK version
└── README.md
```

---

## 10. Open Questions / Next Decisions

- **PDF validation tool**: `pdftotext` (poppler) vs. `pdfplumber` vs. PyMuPDF for the text extraction test (C013).
- **Distribution**: PyPI package vs. Docker vs. clone-and-run. Affects `scripts/setup.sh` design.
- **Database encryption**: At-rest encryption for `flowjob.db` — SQLCipher vs. filesystem-level encryption.
- **Notification mechanism for human approval gate**: terminal prompt vs. OS notification vs. simple web page.
