# FlowJob: Agentic Job Application Pipeline
## Design Specification v1.2

FlowJob is an automated, multi-agent pipeline built on the Google Antigravity SDK. It discovers job postings, analyzes fit, generates tailored resumes, runs editorial QA, and stages applications for human approval. v1.2 adds the **agentic evidence loop**: when the draft can't prove a JD requirement, the pipeline asks the human for evidence via HITL grilling sessions instead of silently under-delivering.

> **v1.2 changes from v1.1**: Agentic evidence loop added — per-run coverage critic, Tailor-as-Writer tool loop, HITL grilling sessions (interviewer), bank hygiene auditor gate, `NEEDS_EVIDENCE` / `UNFIXABLE` job states, yaml-configured round limits, `flowjob grill` and `flowjob audit-bank` commands. See §10.
>
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
[Tailor Agent] (initial structured draft, JSON only)
       │
       ▼
[Evidence Loop] (see §10)
       │ critic → writer fixes → re-critic (max_writer_rounds)
       │ ├─ grill route (watch) → NEEDS_EVIDENCE (park + notify, no session)
       │ ├─ grill route (run)   → [Grilling Session] (HITL, live)
       │ └─ unfixable           → SKIP + notify (UNFIXABLE)
       │ converged
       ▼
[PDF Generator] (Playwright print-to-PDF + text extraction test)
       │
       ▼
[Editor Agent]
       │ fail → back to ANALYZED (max 1 retry)
       │ pass
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
| `flowjob grill <job_id> [--jog]` | Interactive HITL grilling session for one potential gap; `--jog` opens an open-ended memory-jog session. Job must be ANALYZED or NEEDS_EVIDENCE |
| `flowjob audit-bank` | Read-only hygiene audit of all bank bullets: per-bullet pass/fail + reasons + suggested rewrites |
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

Evidence loop (inside DRAFTED, see §10):
DRAFTED → (critic → writer → re-critic) ──converged──► PDF → Editor → EDITED
                                  ├──grill route──► NEEDS_EVIDENCE ──flowjob grill──► DRAFTED
                                  ├──grill cap (must-have)──► UNFIXABLE (skip + notify)
                                  └──unfixable────► UNFIXABLE (terminal, skip + notify)
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
- **Output**: The initial tailored draft as structured JSON (`ResumeOutput`-compatible, §10.4). PDF/HTML generation is deferred until the evidence loop converges and is handled by the DocumentGenerator, not the Tailor agent.
- **PII boundary**: Contact info is NOT passed to this agent. It generates the narrative content only. Contact fields are injected during PDF generation.

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
- **Human approval gate** (C001): Application is staged in `PENDING_APPROVAL` state. Orchestrator notifies user via OS notification (e.g. `notify-send`), then blocks on CLI input. Agent only executes after explicit confirmation.
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

critic:
  model: "qwen/qwen3.8-27b-free"    # evidence judge; falls back to llm.default_model

writer:
  max_writer_rounds: 3         # critic→writer→re-critic rounds before park/grill

grilling:
  model: "qwen/qwen3.8-27b-free"    # interviewer; falls back to llm.default_model
  max_turns_per_gap: 5         # question turns per gap before drop/unfixable

auditor:
  model: "qwen/qwen3.8-27b-free"    # bank hygiene auditor; falls back to llm.default_model
  max_attempts: 3              # re-audit attempts before human escalation

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
│   │   ├── coverage_critic.py # per-run coverage critic (§10.3)
│   │   ├── interviewer.py    # grilling session interviewer (§10.5)
│   │   ├── auditor.py        # bank hygiene auditor (§10.6)
│   │   ├── writer.py         # Tailor in tool-using role (§10.4)
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
│   └── validate_resume.py    # Master resume validation logic
├── master_resume.md           # The user's master resume (gitignored for PII)
├── flowjob.yaml
├── .env                       # gitignored
├── .gitignore
├── pyproject.toml             # uv-managed, pins AGY SDK version
└── README.md
```

---

## 10. Agentic Evidence Loop

The evidence loop makes the pipeline **ask the human for proof** when the tailored draft can't demonstrate a JD requirement. It is deterministic in structure — an orchestrator-driven cycle of critic → writer → grilling — with the LLM confined to its judging, editing, and interviewing roles. Standing rule of this effort: agents never output whole documents — all writes go through tools (§10.4, §10.5).

### 10.1 Overview

```
Initial draft (Tailor, structured JSON) ─┐
                                         ▼
┌─────────────── Evidence Loop ───────────────┐
│  critic ──fix routes──► writer edits ─┐     │
│    │                    ▲            │     │
│    │                    └── re-critic │     │  max_writer_rounds
│    ├──grill route──► NEEDS_EVIDENCE / grilling session (HITL)
│    └──unfixable──► UNFIXABLE (skip + notify)
└─────────────────────────────────────────────┘
                         │ converged
                         ▼
                  PDF generation → Editor → EDITED
```

The loop runs **inside the `DRAFTED` state**, between the initial Tailor draft and the Editor gate. The Editor remains the final quality gate, unchanged (§3.4); the critic is a *semantic evidence judge* that coexists with it sequentially — critic at the front of the loop, Editor at the back.

### 10.2 New job states

| State | Meaning | Terminal? |
|-------|---------|-----------|
| `NEEDS_EVIDENCE` | Job parked awaiting a grilling session (a potential gap was found in watch mode) | No — resumes via `flowjob grill <job_id>` |
| `UNFIXABLE` | Job skipped: critic judged the candidate genuinely unaligned with the job | Yes — skip + notify; distinct from `SKIPPED` (below fit threshold) |

### 10.3 Per-run coverage critic

The **evidence judge** for one job: a single semantic pass over JD + draft + bank that emits a coverage report with per-requirement routing.

- **Inputs**: JD text, the tailored draft as a **plain-text projection of the structured JSON** (never the PDF; the projection is generated locally, no LLM), and the experience bank.
- **Extraction**: `with_structured_output(method="function_calling")`. The critic is read-only (no tools), so the tool-hijack caveat from the tool-calling research does not apply.
- **Checklist source**: both the JD requirements/qualifications **and** responsibilities sections; each item tagged **must-have** vs **nice-to-have**.
- **Coverage rule**: substantive evidence — a draft bullet must *demonstrate* the requirement (action + result), not just mention the keyword.
- **Verdicts**: `addressed` / `partial` (mentioned but not substantiated → fix route) / `unaddressed`.
- **Routing** (per unaddressed/partial requirement): bank lookup is folded into this single semantic pass — no separate deterministic tags/keyword search stage (the earlier bank-search plan was superseded). Per requirement:
  - bank supports it → **fix** (retrieval failure; writer edits with the found bullets)
  - no bank support + plausible for the candidate → **grill** (potential gap)
  - no bank support + implausible nice-to-have → **drop** (recorded in report, not grilled)
  - any must-have with no bank support + implausible → job-level **unfixable** → skip + notify, no edits, no grilling
- **No thresholds**: no score, no coverage %. The critic lists; the Editor gates.

```python
class RequirementCheck(BaseModel):
    requirement: str
    must_have: bool
    verdict: Literal["addressed", "partial", "unaddressed"]
    route: Literal["none", "fix", "grill", "drop"]   # drop = recorded, not grilled
    support: list[str]     # bullet refs (bank or draft) as section+index paths
    note: str

class CoverageReport(BaseModel):
    unfixable: bool        # job-level: skip + notify
    requirements: list[RequirementCheck]
```

### 10.4 Writer loop (Tailor-as-Writer)

The writer is **execution-only**: it never judges routing (critic-owned) and never re-judges unfixability. It drafts once (single structured output), then edits via tools.

- **Draft artifact**: the structured JSON dict (ResumeOutput-compatible) is the per-job draft source of truth (`data/resumes/<job_id>/resume.json`). A local JSON→markdown projection gives the critic its plain-text input each round. The writer mutates the JSON via `edit_resume` (section+index refs matching the critic's `support` refs).
- **Initial draft**: one structured output (the existing Tailor pass), no whole-resume re-emission thereafter.
- **Loop shape**: critic → writer (executes all `fix` routes) → critic re-audit → repeat until no `fix` routes remain or `max_writer_rounds`. Early exit on a round with zero edits. `grill` routes are untouched by fixes and park the job.
- **`request_human_input`**: exactly two triggers — (1) rounds exhausted without convergence (human gets: what was tried, what remains); (2) a fix that cannot be executed (invalid ref, or content that contradicts the draft).
- **Grilling commit**: after the hygiene auditor passes a STAR bullet — commit **bank first, then draft**: `edit_resume(target: "bank", op: "add", tagged bullet)` appends to `master_resume.md`, then `edit_resume(target: "draft", op: "add")` places it.

```python
# Tool signatures — schema-as-final-tool loop (emit_plan always the final call)
edit_resume(target: "draft"|"bank", op: "add"|"replace"|"remove",
            section: str, index: int, tag: str = "", content: str)
request_human_input(question: str, context: str)
emit_plan(edits: list[dict], remaining: list[str],
          needs_human: bool, summary: str)
```

One LLM invocation per round: 0..n `edit_resume` calls, optionally `request_human_input`, always `emit_plan` last. The orchestrator executes the calls locally and parses `emit_plan` to decide the next round.

### 10.5 Grilling session (interviewer)

An interactive **HITL** session, one potential gap per session, that converts the human's answers into a STAR bullet. The agent never stands in for the human's side.

- **Turn 1**: show the JD requirement + why it's a potential gap + the first question, aimed at the **S/T** of STAR. Each subsequent turn: exactly **one question**, aimed at the missing STAR component (A or R), always asking for numbers. No question dumps. Context (JD requirement, gap, prior answers) is re-shown **only on resume**, not every turn.
- **Session length**: `grilling.max_turns_per_gap` (default 5) per gap. On cap, or when the human reports no experience: nice-to-have → drop (recorded only); must-have → unfixable (skip + notify) — matching the critic's verdict vocabulary.
- **Parking**: "don't remember / need to think" → park mid-session, resume later with the transcript intact.
- **STAR conversion**: interviewer converts inline (no separate step) when S-T-A-R are all present or the human ends early. Condensed STAR, 1–2 lines, X-Y-Z framing, ≥1 quantified metric (follow-up for numbers; `~`/ranges/conservative estimates allowed). Always shows the converted bullet → one human confirmation turn → **hygiene auditor** → writer commits (bank, then draft).
- **Manual trigger**: `flowjob grill <job_id>` after fit score (job `ANALYZED`), before the first draft. `--jog` = open-ended memory-jog ("what else didn't you mention?"), same session engine, different opening prompt. Jogged bullets land in the bank before the first draft.
- **Deferred resume**: `flowjob grill <job_id>` on a `NEEDS_EVIDENCE` job picks up the **same gap** with the full transcript in context (no re-asking answered questions). Persistence via LangChain/LangGraph checkpointing to SQLite on the job — the datastore is the source of truth, never in-memory state. Turn cap counts per session-resume.

### 10.6 Bank hygiene auditor

The **evergreen, JD-independent** quality gate: verifies a bullet is well-written before it is committed to the bank. Runs after the grilling session converts + the human confirms, **before** the writer's bank commit.

- **Criteria (all four must pass — binary, no score)**:
  - **C1 Quantified** — ≥1 concrete metric (number, `%`, `~`, range, before→after).
  - **C2 Active** — strong achievement verb opening; bans `responsible for`, `helped with`, `worked on`, `assisted`.
  - **C3 Specific** — names the what (tech/tool/domain/outcome); no vague filler.
  - **C4 Concise** — ≤2 lines.
- **Mechanism (hybrid)**: deterministic fast-fail first — C1 (digit/%/~ regex), C4 (length), C2 (weak-verb regex) → immediate reject with concrete reasons, zero tokens. LLM structured judge (`with_structured_output`) only for the fuzzy residue: C3 specificity + overall verdict.
- **Rejection behavior**: feedback loop to the interviewer (same session, facts unchanged) to revise wording, then re-audit, up to `auditor.max_attempts` (default 3). On exhaustion, escalate to the human (show bullet + `issues`): tweak manually, drop (recorded, not committed), or override. Never silently discard.

```python
class BulletCheck(BaseModel):
    criterion: str   # "C1 Quantified" | "C2 Active" | "C3 Specific" | "C4 Concise"
    passed: bool
    note: str

class BulletAudit(BaseModel):
    passed: bool            # all-or-nothing across checks
    checks: list[BulletCheck]
    issues: list[str]       # concrete, agent/human-actionable rejection reasons

class BankAuditReport(BaseModel):
    audited: list[BulletAudit]
    passed_count: int
    failed_count: int
```

`flowjob audit-bank` runs the auditor over every bank bullet and prints a read-only report (pass/fail + reasons + suggested rewrites). It never modifies `master_resume.md`.

### 10.7 Pipeline integration

- **Slot**: a new `process_evidence_loop` orchestrator step replaces the single-shot draft→edit gap: `DRAFTED` → critic/writer loop → PDF generation → Editor → `EDITED`. Initial Tailor output is the structured JSON; PDF generation is deferred until the loop converges.
- **Watch mode**: critic finds a grill route after the writer loop → job gets `NEEDS_EVIDENCE` + notification, and the pipeline continues to the next job (no blocking). Parked jobs are skipped until a grilling session resolves them.
- **Run mode**: grill route reached → pipeline pauses and runs the grilling session interactively; on session end the loop continues with fresh bank evidence.
- **Notification**: `notify_user(title, message)` helper wrapping the existing `notify-send` pattern (fallback to print when unavailable). Two call sites: `NEEDS_EVIDENCE` assignment — "FlowJob: evidence needed for {title} at {company} — run `flowjob grill <job_id>`" — and `UNFIXABLE` skip — "FlowJob: {title} at {company} skipped (unaligned)".
- **Resume**: grilling success on a `NEEDS_EVIDENCE` job returns it to `DRAFTED`; the evidence loop re-runs with the new bank content.

### 10.8 Configuration (new sections)

The evidence-loop config sections are shown in the full `flowjob.yaml` example in §8 (critic, writer, grilling, auditor). Each agent's `model` falls back to `llm.default_model` when unset.

The three round limits — `writer.max_writer_rounds`, `grilling.max_turns_per_gap`, `auditor.max_attempts` — are the only loop thresholds; the critic deliberately has none.

### 10.9 New agents and files

- `src/agents/coverage_critic.py` — per-run coverage critic (§10.3)
- `src/agents/interviewer.py` — grilling session interviewer (§10.5)
- `src/agents/auditor.py` — bank hygiene auditor (§10.6)
- `src/agents/writer.py` — Tailor agent in its tool-using role (§10.4)
- `flowjob status` counts extended with `NEEDS_EVIDENCE` / `UNFIXABLE`

---

