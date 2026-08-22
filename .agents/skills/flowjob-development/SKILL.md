---
name: flowjob-development
description: Project-specific guidance for building and modifying the FlowJob agentic pipeline. Use this skill whenever the user asks to implement, debug, or modify FlowJob core features, agents, or Playwright adapters.
---

# FlowJob Development Guidelines

You are working on **FlowJob**, an open-source, automated job application pipeline built with the Google Antigravity (AGY) SDK and Python `uv`. 

When implementing or debugging, strictly adhere to the following architecture and constraints:

## 1. Orchestration vs. Agents
- **Hybrid Orchestration:** Do NOT rely on LLMs to decide the pipeline flow (e.g., `start_subagent`). The pipeline is deterministically orchestrated in Python (`Coordinator`). AGY SDK agents (Scout, Analyst, Tailor, Editor, Applicator) are invoked as **processors** via an `AgentRunner` abstraction.
- **State Machine:** SQLite is the single source of truth. All transitions (NEW → ANALYZED → DRAFTED → EDITED → PENDING_APPROVAL → APPLIED) are atomic. In-memory state should not be trusted across restarts.
- **Idempotency:** Every job posting has a unique ID: `sha256(job_url + company + title)[:12]`. Always check SQLite before processing.

## 2. Agent Constraints
- **PII Boundary:** Do NOT pass the user's full contact info to LLMs. The Tailor Agent only receives experience bullets and skills. Contact info (email, phone, etc.) is injected locally during HTML/PDF generation.
- **Editor Agent (Not Checker):** Do NOT try to simulate a proprietary ATS (like Workday or Greenhouse). The Editor Agent performs verifiable QA: keyword coverage, fact-checking against the Master Resume, tone auditing, and grammar.
- **Human Approval:** The pipeline MUST stop at `PENDING_APPROVAL`. The Applicator Agent never fires without explicit user confirmation. Do not build full auto-submit.

## 3. Playwright & Browser Automation
LinkedIn actively fights automation. You must build for resilience:
- **Never Headless:** Always use `headless=False` with a persistent `storageState` to reuse cookies.
- **Locators Only:** Never use static CSS classes (e.g., `.job-card-container`). Use Playwright's Locator API (e.g., `get_by_role("button", name="Easy Apply")` or `get_by_label`).
- **Anti-Detection:** 
  - Inject temporal jitter (randomized polling).
  - Add navigation noise (scroll JDs, pause for 2-5s between clicks, visit company pages).
  - Fail fast on CAPTCHAs or redirect loops. Halt the pipeline; do NOT blindly retry.
- **Unknown Fields:** If the Easy Apply form asks an unrecognized question, take a screenshot, pause the pipeline, and wait for human input. Never guess or hallucinate answers.

## 5. Pipeline architecture (verified Aug 2026)

- **One pipeline implementation.** `src/pipeline/orchestrator.py` (`run_pipeline`) is the production path; `src/pipeline/engine.py` (`PipelineCycleEngine`) duplicated it and was only exercised by unit tests — the tested copy was the dead copy. When touching pipeline logic, first confirm which copy is live via the import graph (`grep -rn "run_pipeline\|PipelineCycleEngine" src tests`), never assume the unit-tested one ships.
- **Test-reality gap warning:** heavy-mock integration tests (`test_orchestrator*.py`, `test_pipeline_e2e.py`) patch 6-8 internals each (`process_scout`, `init_db`, `get_session`, `yaml.safe_load`) — they verify call-wiring, not behaviour, and passed while manual runs failed. New pipeline tests must mock at true seams only (LLM client, browser driver), using real in-memory SQLite + tmp dirs + fake agents.
- **Known friction to not re-create:** config read twice (`load_config` vs raw `yaml.safe_load` inside orchestrator); LLM failover loops hand-rolled per agent around `llm_factory`; watch loop duplicated between `cli.watch` and `tui/watch.py`; TUI back-imports `src.cli.build_agents`; LinkedIn query-URL knowledge split between orchestrator and scout.
- **Refactor conventions for this repo:** staged atomic commits, each leaving `pytest` green; internal interfaces may break freely (update all callers in the same commit).

## 4. Graceful Degradation
- If automation fails, the system must output a **Manual Application Package** (tailored PDF, JD text, suggested answers) so the user can apply themselves.

Always run `flowjob validate` to verify the `master_resume.md` format after any changes to schema parsing.
