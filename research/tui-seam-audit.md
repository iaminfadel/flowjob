# Research: Pipeline HITL Seam Audit for TUI

> Resolves [#84](https://github.com/iaminfadel/flowjob/issues/84)

## Sources

- Read of all pipeline/agent/CLI source in `src/` (orchestrator, interviewer, applicator, cli, db/store, db/models, tools/browser, agents/llm_factory, agents/structured_llm)
- `design_spec.md` (intended seams C001 approval gate, unknown-field `form_signature_log`, `request_human_input`)
- `tests/integration/test_evidence_loop_e2e.py` (existing programmatic grilling seam)
- Reference research note: `research/ats-scoring-ai-screening.md` (style)

## Goal

A future TUI runs the pipeline in-process on background threads (Textual workers) and must host: the approval gate, grilling sessions, unknown-form-field pauses, and the watch loop. This audit maps every blocking HITL / I/O point, with the minimal adapter seam for each. **Front-end only: no pipeline semantics change.**

## 1. Seam Inventory (all blocking points)

| # | Location | What blocks | Current seam | Minimal TUI seam |
|---|----------|-------------|--------------|------------------|
| S1 | `src/pipeline/orchestrator.py:263` (live def at 259–266) | `input("Do you approve applying to this job? (y/n): ")` — approval gate | None (stdin) | Add optional `approval_fn: Callable[[Job], bool]` param through `run_pipeline` → `process_pending_approval_jobs` → `_step`; TUI passes a queue-driven callback |
| S2 | `src/pipeline/orchestrator.py:165–173` | **Dead duplicate** `prompt_user_approval` — shadowed by the def at 259 (later in module scope) | — | Delete; keeps the gate single-sourced |
| S3 | `src/agents/interviewer.py:165,185,211` | `input_fn(...)` — 3 call sites (candidate answer, bullet accept y/n/edit, custom bullet edit) | `input_fn: Callable[[str], str] = input` param (line 119) + `interactive: bool` param (line 120) | **Already threaded-ready**: pass an async-aware callback (`queue.get`-style). Note: `interactive` is declared but never read in the body — dead param |
| S4 | `src/agents/applicator.py:92–94` | `input("Press Enter once you have filled the field and clicked Next/Review... ")` — unknown-field pause, inside open `sync_playwright` context | None (stdin) | Add an injected wait callback (e.g. `wait_fn: Callable[[str], None]`) defaulting to `input`; screenshot at `browser_data/unknown_field.png` (line 87–88) gives the TUI its "what to fix" view |
| S5 | `src/tools/browser.py:16` | `page.wait_for_event("close", timeout=0)` — `login_linkedin` blocks until the user closes the browser | None | TUI hosts login in a worker thread; no seam change needed, but must run off the TUI event loop |
| S6 | `src/pipeline/orchestrator.py:468–471` | `check_session_health()` launches a headed Playwright browser (blocking, ~45s worst case) and **`sys.exit(1)` kills the process** on failure | None | Replace `sys.exit(1)` with a raised exception or `False` return — in-process TUI must not die |
| S7 | `src/pipeline/orchestrator.py:473–474` | `open("flowjob.yaml")` — hardcoded cwd-relative config read | None | TUI runs with repo cwd (same as CLI today); optional `config_path` param later |

Non-blocking but TUI-relevant output sinks: `print()` is used everywhere in `src/` (orchestrator, interviewer, applicator, browser). A TUI log pane needs stdout capture (redirect `sys.stdout` in the worker) or a `print`-replacement hook.

## 2. Approval Gate (`prompt_user_approval`)

- **Live signature**: `def prompt_user_approval(job) -> bool` — `src/pipeline/orchestrator.py:259`
- **Behavior**: `notify_user(...)` (line 261) then `input("Do you approve applying to this job? (y/n): ")` (line 263); returns `True` only on a "y" answer; `(EOFError, KeyboardInterrupt)` → `False` (line 265–266).
- **Call path**: `run_pipeline` (line 490) → `process_pending_approval_jobs` (line 442) → `_step` closure (line 451) → `prompt_user_approval(j)`; on `True` → `applicator_agent.run(j)` → `APPLIED`/`FAILED`; on `False` → `SKIPPED` (line 459–461).
- **Gate semantics**: always prompts. `config.py:40` declares `require_approval: bool = True` (also `flowjob.yaml:35`) but **no code reads it** — the flag is dead configuration; the gate is unconditional. `dry_run` is the only escape (orchestrator.py:489).
- **Seam**: `approval_fn` callback threaded from `run_pipeline` → `process_pending_approval_jobs`; TUI renders a modal and resolves a queue/`asyncio.Event`. `notify_user` stays as-is (harmless `notify-send` + print fallback).

## 3. Grilling Session (`run_grilling_session`)

- **Signature**: `src/agents/interviewer.py:116–125`
  `run_grilling_session(session, job_id, input_fn: Callable[[str], str] = input, interactive: bool = True, model_name="google/gemini-2.5-pro", max_turns_per_gap=5, llm=None, providers=None) -> bool`
- **Interactive I/O**: three `input_fn(...)` calls — candidate answer (line 165), bullet accept `y/n/edit` (line 185), custom bullet (line 211). `interactive` is **never referenced in the body** — the real switch is `input_fn`.
- **Transcript persistence (checkpointing)**: every turn is committed to `job.grilling_transcript` (JSON column, `src/db/models.py:38`) via `session.add` + `session.commit` (lines 162–163, 169–171, 175–177, 205–207, 224–226). Shape: `{"active_requirement": str, "gaps": {requirement: {"status": "pending"|"completed"|"dropped", "turns": [{role, text}], "must_have": bool, "synthesized_bullet": str}}}` (see orchestrator.py:341–352 for the parking shape).
- **Resume semantics**: skips `completed`/`dropped` gaps (line 148); loop cap `len(turns) < max_turns_per_gap * 2` (line 154); when all gaps resolve → `job.state = DRAFTED` (line 231–234), which lets the next evidence-loop pass converge.
- **Programmatic drive**: already supported and covered by `tests/integration/test_evidence_loop_e2e.py:234–242` (mock `input_fn` fed from an iterator). **TUI seam: zero pipeline change** — pass a callback that yields answers via `queue.get()` from the worker thread. Caveat: `input_fn` is a plain synchronous call; the TUI needs the worker thread to block on its own queue (Textual `run_worker(thread=True)` is fine).
- **Missing piece**: no notification/callback on session start/finish — TUI can detect via `job.state` / transcript polling, or a wrapper around the call.

## 4. Applicator Unknown-Field Pause

- **Where**: `src/agents/applicator.py:58–97` inside the Easy-Apply modal loop, after clicking Next/Review when a `role="alert"` error appears (line 83–85).
- **Screenshot**: `page.screenshot(path=os.path.join(browser_data_dir, "unknown_field.png"))` (line 87–88), printed to stdout (line 89).
- **Block**: `input("Press Enter once you have filled the field and clicked Next/Review... ")` (line 94) — the browser stays open on the paused form, so the human fills the field in the visible window, then the loop re-checks buttons.
- **Answer persistence**: **none today.** The `form_signature_log` described in `design_spec.md:201` (per-company known-answer reuse) is **not implemented** — no field answers are stored anywhere. Only the screenshot survives, and it is overwritten per pause.
- **Seam**: inject a `pause_callback: Callable[[str], None] = input` (or an `on_unknown_field(question/screenshot_path)` event + blocking resume) so the TUI can surface the screenshot and an "I fixed it" button instead of stdin. Playwright is `sync_api` — the pause must stay inside the same worker thread; a TUI thread blocked on `queue.get()` keeps the browser alive correctly.

## 5. `notify_user` Call Sites

Helper: `src/pipeline/orchestrator.py:253–257` — `notify_user(title, message)` → `subprocess.run(["notify-send", ...])` with `print("[NOTIFICATION] ...")` fallback on failure.

| Site | Location | When |
|------|----------|------|
| Approval gate | `orchestrator.py:261` | Job is `PENDING_APPROVAL`, gate about to block |
| UNFIXABLE skip | `orchestrator.py:323` | Critic marks draft unfixable → `JobState.UNFIXABLE` |
| Evidence needed | `orchestrator.py:353` | Critic routes ≥1 gap to `grill` → `JobState.NEEDS_EVIDENCE`, transcript parked |

All fire from the pipeline worker thread; TUI can either keep `notify-send` or route to an in-app toast via a callback seam. No other notification helper exists in `src/`.

## 6. `run_pipeline` — Signature, Blocking, Events, Thread Safety

- **Signature**: `run_pipeline(agents: dict, url: str = None, dry_run: bool = False, doc_generator=None)` — `orchestrator.py:465`. **Returns `None`** (implicit); the only persisted outcome is a `PipelineRun` row on success (line 492–494).
- **Blocking sequence** (all synchronous, one session): session health probe w/ headed browser + `sys.exit(1)` (468–471) → config + `init_db` (473–477) → `get_session(engine)` (479) → scout (network scrape) → retries → analyst → tailor → evidence loop → editor → move to `PENDING_APPROVAL` → (unless `dry_run`) approval gate `input()` + applicator Playwright run + `PipelineRun` record.
- **Progress/events**: **none** — no callback, no emitter, no return metadata. Progress is only `print()` output + DB state mutations per job. A TUI can either capture stdout, or poll `Job.state` in the same DB.
- **In-process safety**:
  - `init_db` (`src/db/store.py:3–15`) is **idempotent** — `SQLModel.metadata.create_all(engine)` only, no drops (commit `ec56b02` fixed the wipe). Safe to call repeatedly / from a thread.
  - `get_session` (`store.py:17–19`) returns a fresh `Session` per call — do **not** share one session across threads; the pipeline's session lives entirely within one worker thread (fine).
  - `log_interaction` (`src/agents/llm_factory.py:141–186`) opens its own short `Session(engine)` per LLM call with a module-cached engine (`_engine`, line 134–138) — independent of the pipeline session, so LLM logging works from any thread.
  - **SQLite caveat**: plain `sqlite:///` engine, no WAL, no busy timeout. The pipeline writes from one worker while the TUI reads (status/logs/grill list) from the main thread → under write load a TUI read can hit `database is locked` (default 5s timeout). Seam: `PRAGMA journal_mode=WAL` + `busy_timeout` on the engine, or route all TUI reads through a single short-lived session with retry.
  - **Kill-switches to remove for in-process use**: `sys.exit(1)` at `orchestrator.py:471` (session health) — this would terminate the TUI host.
  - Agents (`build_agents`, `cli.py:55–84`) are construct-once objects with no per-run mutable state beyond the LLM client; safe to reuse across cycles from one thread.

## 7. Watch Loop

- **Lives in the CLI, not the orchestrator**: `src/cli.py:96–110` (`watch` command). Loop: `while True: run_pipeline(agents)` → `jitter_minutes = random.uniform(45, 90)` (line 108) → `time.sleep(jitter_minutes * 60)` (line 110). The 45–90 min uniform jitter matches `design_spec.md:212`.
- **TUI-hosted version**: needs (a) `run_pipeline` made non-process-killing (S6), (b) the sleep replaced by an async `asyncio.sleep` / `Timer` in a Textual worker (blocking `time.sleep` would stall the worker only — acceptable, but async is cleaner), (c) jitter constant configurable via `flowjob.yaml` if desired. No orchestrator change required; the loop itself is trivially relocatable.

## 8. `LLMInteraction` Reads (logs viewer) and Existing Queries

- **Write side**: `invoke_llm` (`src/agents/llm_factory.py:247–293`) persists every request via `log_interaction` (fields per `src/db/models.py:58–75`: timestamp, agent_name, job_id, provider, model, prompt/response (truncated 200k), extracted JSON, prompt/completion/cached tokens, cost_usd, latency_ms, success, error).
- **Read side today** (`src/cli.py logs`, 226–291):
  - Filters: `job_id` (247), `agent_name` (249); ordered `id.desc()` with `limit` (274).
  - **Cost/aggregation** (251–272): totals for cost, tokens, cached tokens, failure count, and a per-provider breakdown `{calls, cost, tokens, cached}`.
  - Raw mode: prompt/response first 2000 chars (289–291).
- **Status query** (`src/cli.py status`, 112–157): per-`JobState` counts via `select(func.count(Job.id)).where(Job.state == ...)` (128–140) + last `PipelineRun` timestamp (143–145).
- **TUI logs viewer seam**: none needed — reuse the same `select(LLMInteraction)` queries against a short-lived session. Aggregations already exist as inline Python; extract to `src/db/queries.py` only if shared between CLI and TUI.
- **Other DB reads**: `grill` listing (`cli.py:202–212`) selects `JobState.NEEDS_EVIDENCE` jobs; `process_*` stages each `select(Job).where(Job.state == ...)`.

## 9. Other `input()` / stdin / `typer.prompt` Blocking Calls

Full sweep of `src/` + `scripts/`:

| Location | Call | Context |
|----------|------|---------|
| `orchestrator.py:172` | `input(...)` | Dead code (shadowed duplicate def, S2) |
| `orchestrator.py:263` | `input(...)` | Live approval gate (S1) |
| `interviewer.py:165, 185, 211` | `input_fn(...)` | Grilling session (S3) |
| `applicator.py:94` | `input(...)` | Unknown-field pause (S4) |
| `browser.py:16` | `page.wait_for_event("close")` | `login_linkedin` — blocks on browser close, not stdin (S5) |

No `typer.prompt`, `getpass`, or `sys.stdin` reads anywhere. `scripts/` has zero blocking input. CLI exit points (`cli.py:28,34,43`) are `validate`-command only and irrelevant to the TUI.

## 10. In-Process Threaded Safety Verdict

**Conditionally safe** to host in a single background thread (Textual `run_worker(thread=True)`), with four minimal, semantics-preserving changes:

1. **Kill the process-killers**: replace `sys.exit(1)` in `run_pipeline` (`orchestrator.py:471`) with a raised exception — the only thing that would take the TUI down with it.
2. **Thread the two stdin seams**: `approval_fn` into the approval gate (S1) and a wait callback into the applicator pause (S4). Grilling needs **zero** change — `input_fn` already exists and is test-proven.
3. **DB concurrency**: keep one writer thread; TUI reads use short-lived sessions; add WAL + `busy_timeout` to the engine (or accept rare lock errors on read).
4. **Output capture**: capture `print()` from the worker (stdout redirect) or add a `log_fn` hook, since all progress reporting is print-based.

No pipeline semantics change required — the grilling seam is already in place (`interviewer.py:119`), the approval/applicator seams are new 3-line-injection points, and everything else (watch loop, logs, status) is TUI-side.

## 11. Additional Findings (drift / dead code)

- `require_approval` config (`config.py:40`, `flowjob.yaml:35`) is **never read** — gate always blocks. Either wire it into `run_pipeline` or drop it.
- Duplicate `prompt_user_approval` defs at `orchestrator.py:165` and `259` — line 165 is dead.
- `interactive` param of `run_grilling_session` (`interviewer.py:120`) is unused.
- `form_signature_log` (design_spec.md:201) is unimplemented — no form-answer persistence exists; TUI screenshot surfacing has no answer-reuse backend to hook into yet.
- Cwd-relative paths throughout (`flowjob.yaml`, `flowjob.db`, `browser_data/`, `data/resumes/`) — TUI must launch with the repo as working directory.
