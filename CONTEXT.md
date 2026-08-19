# FlowJob

FlowJob is an agentic job-application pipeline: deterministic Python orchestrates Scout, Analyst, Tailor, Editor, and Applicator processors over SQLite job state. This effort adds the evidence loop that lets the pipeline ask the human when it lacks proof.

## Language

**Experience bank**:
The user's master resume (`master_resume.md`) — the single source of truth: YAML metadata plus tagged narrative bullets.
_Avoid_: master resume (ambiguous with the file), source resume, CV

**Bullet**:
A single achievement line in the bank or a tailored draft, optionally tagged `[tag]`.

**Bullet ref**:
A canonical reference string identifying a specific bullet in the bank (`bank:<Company>:<bullet_index>`) or in the draft (`draft:<dot_path>.<bullet_index>`).

**Draft**:
The structured JSON resume being tailored for one job — the artifact the writer edits via tools; the critic audits it through a local plain-text (markdown) projection, never the PDF.

**Per-run critic**:
The evidence judge for one job: audits a tailored draft (plain text, never the PDF) against its JD — both its requirements and responsibilities sections, each tagged must-have or nice-to-have — then checks the bank and routes each unaddressed requirement: fix (bank supports it — writer edits with the found bullets), grill (potential gap), drop (implausible nice-to-have — recorded only), or job-level unfixable (skip + notify).
_Avoid_: critic (ambiguous), checker, QA

**Coverage report**:
The per-run critic's output: one entry per JD requirement — requirement, must-have tag, verdict, routing, supporting bullet refs, note — plus a job-level unfixable flag.

**Potential gap**:
An unaddressed JD requirement with no supporting evidence in the bank, judged plausible for the candidate — the trigger for a grilling session.
_Avoid_: gap (ambiguous), unwritten experience

**Bank hygiene auditor**:
The evergreen, JD-independent checker that verifies a bullet is well-written (quantified, specific, not vague filler) before it is committed to the bank.
_Avoid_: critic, quality gate

**Retrieval failure**:
A JD requirement the bank can support but the writer left out of the draft — fixed by the writer alone, no human needed.
_Avoid_: gap

**Missing evidence**:
A JD requirement with zero supporting evidence anywhere in the bank — a true content gap; if judged plausible for the candidate it becomes a potential gap and triggers a grilling session.
_Avoid_: gap (ambiguous)

**Grilling session**:
An interactive HITL interview in which an interviewer agent asks the human targeted questions about a potential gap and converts the answers into a STAR bullet.
_Avoid_: interview, Q&A

**Interviewer**:
The agent that runs a grilling session — one targeted question per turn, aimed at the missing STAR component; converts answers into a STAR bullet and shows it for confirmation before it is committed.
_Avoid_: interviewer agent, chat agent

**Session transcript**:
The persisted record of a grilling session (the checkpoint), stored on the job so a deferred session resumes in-context without re-asking answered questions. The source of truth is the datastore, never in-memory state.

**STAR bullet**:
A condensed Situation-Task-Action-Result bullet suitable for a resume. Distinct from a full STAR story (interview-prep material).

**Writer**:
The Tailor agent in its tool-using role — it drafts once (single structured output), then fixes retrieval failures and commits grilling output via `edit_resume` (draft or bank); `request_human_input` when the loop cannot converge or a fix cannot be executed. Never outputs whole documents; edits via tools.
_Avoid_: tailor (kept for the drafting role), editor

**Unfixable**:
The per-run critic's job-level judgment that the user is genuinely unaligned with the job and the resume cannot be made to fit — the pipeline skips the job and notifies the user. Distinct from a fixable gap, which goes to grilling. The job's state is `UNFIXABLE`.

**NEEDS_EVIDENCE**:
Job state when a missing-evidence gap is found in a watch session — the job is parked, the user notified, and the pipeline continues with the rest of the queue.

**Manual application**:
A job application filed by the human directly, outside the pipeline — logged with slim, all-optional details (title, company, url, date applied, cv, state, notes, job description). The pipeline never processes it.
_Avoid_: manual job (ambiguous with the Job row), hand application

**Pipeline application**:
A job application filed by the Applicator agent through the normal pipeline — carries the full artifact set (jd, fit/edit scores, tailor metadata, grilling transcript).
_Avoid_: auto application, automated application

**Watch session**:
The continuous hosting of the pipeline's repeated cycles, separated by jittered countdowns, from manual start to stop — never started automatically on cockpit launch. `flowjob watch` is the CLI-only equivalent; the two never run concurrently.
_Avoid_: watch mode, watcher

**Cycle**:
One full pipeline run within a watch session — scout through applicator over the current job queue.
_Avoid_: run (ambiguous with the persisted pipeline run record), pipeline cycle

**Countdown**:
The jittered wait between cycles within a watch session — a random draw between a configured minimum and maximum wait (default 45–90 minutes).
_Avoid_: sleep, jitter period

**Cycle summary**:
The outcome record of one cycle — applied/skipped/unfixable/failed counts, duration, and LLM spend delta — shown in the watch area at cycle end.