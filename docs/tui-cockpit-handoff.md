# TUI Cockpit — Implementation Handoff

Wayfinding complete (2026-08-18). All decision tickets on the map are closed:
[Map: FlowJob TUI cockpit](https://github.com/iaminfadel/flowjob/issues/82) is the canonical
index — **read its Decisions-so-far first**, then this document for the build surface.

## Destination

A full-screen Textual TUI cockpit (`flowjob tui`): dashboard (state counts, last cycle, LLM
spend), job browser with per-state filters + detail pane, LLM log viewer, settings editor
(structured forms), and in-TUI HITL flows (approval gate, grilling, unknown-field pauses).
Hosts the watch loop with live progress and stop/start. **Front-end only**: no pipeline
semantics change, no agent changes, no DB schema change, no config format change — single
boss-approved exception: the new `watch:` jitter keys.

## Locked decisions (with ticket links)

- **Stack**: Textual `>=8.2,<9` (8.2.8 verified; Py>=3.9, 3.12 OK); `ruamel.yaml` for settings
  write-back (new deps). [Research: Textual API landscape #83], [Grilling: Settings save semantics #88]
- **In-process pipeline** via Textual `@work(thread=True)` workers + `post_message`;
  `run_in_thread` doesn't exist. [Research: Textual API landscape #83]
- **Pipeline-triggered job actions only** — no free-form state pokes. [Map Notes #82]
- **Screens**: Variant A — TabbedContent, tabs 1-5, Footer hints for all bindings, ASCII logo.
  [Prototype: Cockpit screen layout #85]
- **Watch hosting**: manual start / graceful stop / restart, no auto-start; TUI countdown
  (mm:ss + bar, "Run now"); stdout-capture progress; per-cycle summary line; error state w/
  restart; jitter via `watch:` yaml keys (defaults 45-90). [Grilling: Watch-mode hosting #86]
- **Approval gate**: in-TUI modal via `approval_fn` seam; `notify-send` kept. [Grilling: Watch-mode hosting #86]
- **Actions matrix + detail pane**: per-state actions and pane sections. [Grilling: Job actions matrix #87]
- **Settings save semantics**: ruamel round-trip, pre-write validation, atomic write, env
  override banner, guardrails. [Grilling: Settings save semantics #88]

## Seams to implement (from the HITL seam audit, #84 — all approved)

1. `approval_fn: Callable[[Job], bool]` threaded `run_pipeline` → `process_pending_approval_jobs`
   → `_step`, defaulting to today's stdin gate (orchestrator.py:259-266). TUI passes a
   queue-driven callback; modal + `notify-send`.
2. Applicator unknown-field pause: inject `wait_fn: Callable[[str], None]` defaulting to
   `input` (applicator.py:92-94); screenshot already at `browser_data/unknown_field.png`
   (overwritten per pause — fine). TUI worker blocks on its queue; browser stays open.
3. `sys.exit(1)` → raise (orchestrator.py:471) — in-process TUI must not die.
4. SQLite: `PRAGMA journal_mode=WAL` + `busy_timeout` on the engine (store.py) — TUI reads
   from short-lived sessions, pipeline writes from one worker thread.
5. Stdout capture: redirect `sys.stdout` in the worker → RichLog tail + watch status.
6. Grilling: **zero pipeline change** — `run_grilling_session(input_fn=...)` already
   parameterized (interviewer.py:116-125); TUI blocks on a queue in a worker.
7. Retry re-queue helper (TUI-side): set state per `ErrorRecord.agent_name`
   (Analyst→NEW, Tailor→ANALYZED, Critic/Writer/Editor→DRAFTED, Applicator→PENDING_APPROVAL)
   + reset `retry_count` to 0; next cycle's `process_retries` executes the work.
8. `WatchConfig` model (`min_wait_minutes`, `max_wait_minutes`) added to `src/config.py` +
   `watch:` in `FlowJobConfig`; read by `flowjob watch` and the TUI.
9. Watch loop relocated from cli.py:96-110 into the TUI worker; `.flowjob-watch.lock`
   gates CLI/TUI coexistence.

## Screens (Variant A, from #85)

- **Dashboard** (1): stat cards + state counts + watch row (status, countdown, start/stop).
- **Jobs** (2): state filter (Select) + full-width DataTable (Title/Company/Location/State/
  Fit/Edit), row-select → detail pane (see #87).
- **LLM Logs** (3): RichLog + spend totals; reuse `select(LLMInteraction)` queries and the
  aggregation logic from cli.py logs (extract to `src/db/queries.py` if shared).
- **Settings** (4): structured forms for all sections **except `llm.providers`** (manual YAML);
  includes the new `watch:` section. See save semantics (#88).
- **HITL** (5): approval inbox + grilling chat side-by-side.

Keyboard-first with visible Footer hints is a settled boss preference. Approve/reject/retry
refresh jobs table + dashboard counts.

## Actions matrix (from #87)

| State | Actions |
|---|---|
| NEW, ANALYZED, DRAFTED, EDITED | view only |
| PENDING_APPROVAL | Approve / Reject (gate-False → SKIPPED; REJECTED enum stays dead), open URL, open resume dir |
| NEEDS_EVIDENCE | Open grill (worker-hosted chat, `input_fn` queue, transcript checkpointed per turn), view gaps |
| FAILED, TAILOR_FAIL, EDIT_FAIL | Retry (re-queue per agent + reset retry_count), view error block (ErrorRecord: agent/type/stack/count) |
| APPLIED, SKIPPED, UNFIXABLE, REJECTED | view only |
| all | open URL; open resume dir `data/resumes/<job_id>/` when `cv_path` set |

Detail pane: always meta (location, posted, URL) + state/fit/edit scores + JD; conditional —
grilling transcript with per-gap status badges (pending/completed/dropped), error block for
fail states, cv/resume-dir line. Actions live in both the HITL inbox and the detail pane (one
implementation). Note: the design-spec "manual application package" (`output/…` with jd.txt +
suggested_answers.txt) is **not implemented** — open-dir points at the real artifact dir.

## Settings save semantics (from #88)

- ruamel.yaml round-trip (comments/order preserved; providers block never touched).
- Pre-write validation: `FlowJobConfig(**new_dict)`; on error, field-level messages, no write.
  Load stays tolerant (`extra='ignore'`).
- Atomic write: temp file + `os.replace` + fsync.
- Env overrides (`FLOWJOB_MODEL` / `OPENROUTER_API_KEY` / `.env`): form shows effective values,
  edits write file values; banner "env override active — model edits won't take effect until
  unset"; warn not block.
- Post-save: auto config round-trip; manual "Re-validate" button runs full `flowjob validate`
  (config + master_resume.md + DB init), never auto.
- Guardrails (block save + message): fit/coverage 0-100; max_apps_per_day 1-500;
  max_apps_per_hour 1-24; writer rounds/turns/attempts 1-10; llm_timeout 5-600; retries 0-10;
  retention 1-3650; scrape 1-500; cross-field app/hour ≤ and watch min < max. Paths/URLs/models
  free text.

## Watch hosting (from #86)

Manual start / graceful stop / restart; no auto-start on launch; countdown mm:ss + bar +
"Run now"; stdout-capture → RichLog tail + watch status; per-cycle summary (counts, duration,
spend delta); error state with manual restart; lockfile `.flowjob-watch.lock` gates CLI/TUI
coexistence; `watch:` yaml keys `min_wait_minutes`/`max_wait_minutes` read by both
`flowjob watch` and the TUI (CLI + settings form, warn not block, defaults 45-90).
NEEDS_EVIDENCE/UNFIXABLE → toast + HITL inbox; browser/login watch states surfaced.

## Testing

- Textual Pilot (`App.run_test()` + press/click/pause) for critical flows: approval modal
  approve/reject, grill session chat, watch start/stop, settings save + validation error.
- Unit tests: save semantics (ruamel round-trip preserves comments), retry re-queue mapping,
  guardrail bounds, atomic write.
- Optional: pytest-textual-snapshot for visual regressions.
- Existing suites must stay green (uv run pytest).

## Build order (suggestion)

1. Seams in pipeline (1-5, 8-9 above) — shipable as semantic-preserving prereqs.
2. Skeleton app: tabs, bindings, footer, dashboard + jobs table from DB.
3. Detail pane + actions matrix (retry helper, approve/reject via seam, open URL/dir).
4. HITL tab: approval inbox modal + grilling chat (input_fn queue).
5. Watch hosting in TUI + lockfile + jitter keys in CLI.
6. Settings forms + save semantics + guardrails.
7. LLM logs viewer + spend.
8. Pilot tests for critical flows; AGENTS.md TUI-rule compliance sweep.

## Open UX items (still to design — not blocked)

Approval-modal visual design and unknown-field pause hosting UX (screenshot surfacing +
"I fixed it" button) — decided at the seam level, not the widget level yet.

## Out of scope

Web UI, CLI redesign, agent behavior changes, DB schema changes, config format changes
(beyond `watch:`), free-form state pokes, raw YAML editor in the TUI, dead-code cleanup
(deferred until after the cockpit ships: dead `prompt_user_approval` dup at orchestrator.py:165,
unused `require_approval` config, unused `interactive` param).
