# DeepSeek Harness (dsh) — Architecture & Paper Notes

Research date: 2026-08-18. Sources: `github.com/deepseek-ai/deepseek-harness` (raw files on `master`, no clone), `github.com/cordiverse/paper` (paper.pdf via pdftotext). Both are works in progress; quotes may drift.

## What it is

- Open-sourced 2026-08-13, MIT license, ~453K lines TypeScript, "developer preview" — README warns breaking changes and no stability guarantees.
- Run with `npx @deepseek-ai/dsh web` → browser UI at `http://127.0.0.1:3080`.
- Two launch shapes: `dsh-web-app` (browser) and `dsh-headless` (one-shot runner, no server).
- Built on **Cordis v4** (vendored as `@deepseek-ai/cordis`, a forked npm scope with a `verify-vendored-links` hygiene gate). Everything is a plugin, composed from layers.
- **Zero eval claims** — `BENCHMARK.md` is a 3-line stub pointing at the Python SDK's `jsonrpc-agent` minimal variant. It is a harness/runtime, not a model or an eval.

## Architecture (from `docs/architecture.md`)

- **Profile** = named composition: a list of bundles + a `cordis.patch.yml`. `dsh-base` is always the first layer (model adapters, tools, persistence, sandbox, approval policy, settings, credentials, telemetry); web/headless ship as templates.
- **Bundle** = distribution format; `dsh.profile` / `dsh.bundle` package.json fields mark the package kind.
- Layer order: bundles in profile order → profile `cordis.patch.yml` → home-level config.

## Interesting design pieces (code-level, file by file)

- `packages/core/agent-loop/src/invariant.ts` — **request-reconstruction invariant** enforced by a listener that must be PREPENDED to the LLM stream hook (prevents a replay listener from short-circuiting live requests). Checks: request object frozen; `sessionId` present and the session live; `step/start` exists in the session log; `foldRequestHeader(request)` equals the logged `request/header` event; and `JSON.stringify(options.messages) === JSON.stringify(session.deriveMessages())` — the outgoing payload must equal what the session log would replay. This is the "session log is the single source of truth" rule made executable.
- `packages/core/session/src/surface.ts` — session surface layer: append-only log is the source of truth. `SURFACE_EVENT_TYPES = user/message | assistant/message | tool/result`. `isSurfaceEvent` requires a `surfaceOp` marker; `isAppendSurfaceEvent` distinguishes append-origin events from replacement copies (replacement copies stay model-only, append-origin ones go to the human transcript). Deliberately browser-safe (no `node:` imports, vite-bundleable).
- `packages/llm/llm-deepseek/src/adapter.ts` — transport-only fetch+SSE adapter. `DeepSeekCatalogModel` (id/name/description/contextWindow/maxTokens); connection facts resolved via thunk once per operation; bearer token via per-request resolver; plugin owns validation/layering/credential policy. Error codes: `CONTEXT_WINDOW_EXCEEDED_CODE`, `QUOTA_EXCEEDED_CODE`; idle watchdog + timeout.
- `packages/sandbox/sandbox/src/index.ts` — `SandboxMode = read-only | workspace-write | danger-full-access`; `SandboxExecutionPolicy` (mode, workspaceRoot, sessionId). Same-world process confinement seam: containers/microVMs/remote execution replace it.
- `packages/sandbox/sandbox/src/escalation.ts` — `WIDER_MODES` strictly-wider ladder (read-only → workspace-write → danger-full-access); `ESCALATION_TARGETS` closed vocabulary; `approveEscalation` is fail-closed and runs BEFORE execution; `EscalationAsk` is a structural function shape (closure over `ctx.approval.request`) so the sandbox package has no dependency on the approval package.
- `packages/core/tools/src/index.ts` — tool execution pipeline: `pre/guard/around/post/result`; "code-mode" uses `createRunCodeTool` (`RUN_CODE_NAME`) with `tools:sdk` section and per-language renderers (`SDK_SECTION_ORDER`, Language → SDK).
- `vendor/README.md` — the vendoring hygiene story: `@deepseek-ai` scoping, `verify-vendored-links`, Schemastery conditional-exports map.

## The paper ("A Programming Paradigm for Spatiotemporal Composability")

- Authors: Yifan Shi (PKU) 1, Wei Zhang (PKU), Tianyi Cui (DeepSeek-AI). 88 pages, preprint draft Aug 13 2026. Footnotes and case-study numbers are dated June 2026.
- Thesis: modern dynamic composition (plugin systems, self-evolving agent harnesses) has two orthogonal dimensions:
  - **Temporal composability** — removing a component must completely and safely revert its side effects.
  - **Spatial composability** — components declare, discover, resolve dependencies reactively.
- Mechanisms (the paper's two core lifts):
  - **Revertible effects** (§3.1): every context transformation carries an explicit inverse; the runtime tracks them and composes inverses so the context is recovered on removal. (Runtime ≠ compile-time effect systems.)
  - **Reactive coeffects** (§3.2): a component declares required coeffects as a spec; context changes notify it as activating / deactivating / neutral.
  - **Unified context** (§3.3): one context type for both; observational equivalence on coeffects gives effects independence.
- **Calculus** (§4): component = triple (dependency spec, provision keys, effect function + inverse); instantiation = fiber with lifecycle (Inactive ⇄ Active; L-Unload/L-Reload); metatheory: preservation, temporal composability, spatial composability, progress, confluence — carried from single component to whole interleaved system.
- **Implementation** (§5): Cordis core library (effect tracking, coeffect resolution, lifecycle, context access), declarative component loader (config reconciliation + HMR), case study: **Koishi** — 4000+ community plugins, 4 years, server + browser console as independent Cordis apps. Notable: an orchestrator disables plugins from the console and effects are withdrawn in place; HMR re-applies edited plugins on save while preserving caches/connections. Disabling a plugin does NOT restart the host.
- **Discussion** (§6): system boundary (inside = exclusive+restorable → tracked/recovered; outside = idΓ → untracked); acquisition vs emission (only acquisition is revertible; emissions need withholding or compensation); capability-based access control via declaration + interception (complete capability set known before load → orchestrator reviews at load time); sandboxing needs an external mechanism (SFI, separate runtime, process, container) — host side of the bridge is an ordinary fiber with attenuated capabilities; language independence (temporal needs closures + module registry / dlopen-dlclose; spatial = DI, TypeScript module augmentation extends the context type).

## Paper ↔ dsh mapping (how the harness uses the paradigm)

- Session log = the effect/coeffect context; `deriveMessages()` is context read-off; the invariant in `invariant.ts` is the runtime checking that emitted requests match the context.
- Surface events (user/message, assistant/message, tool/result) = the coeffect/effect vocabulary of the agent loop.
- Bundles/profiles = components + declarative loader with config reconciliation (cordis.patch.yml layering).
- Sandbox modes + escalation ladder = capability attenuation from §6.3 (interception on the context, approval before execution).
- `dsh-headless` = one-shot fiber activation; web app = long-lived fiber set.
- The paper's self-evolving-harness motivation (§1.2.2) is literally dsh: tools generated and deployed by the model at runtime, needing withdrawable effects (temporal) and declared dependencies (spatial), because restart-on-change kills in-flight tasks and can disable the very process needed to recover.

## What's useful for FlowJob (applied takeaways)

Ranked by leverage for a job-application pipeline (not a coding agent):

1. **Acquisition vs emission** (paper §6.1) — the single most valuable idea. Local effects (DB writes, transcript append) = *acquisition*: reversible, safe to retry. External effects (submitting an application, sending an email) = *emission*: irreversible, NEVER blindly retried. Consequence for FlowJob:
   - Retry logic (retry.py) must distinguish: acquisitions are retryable, emissions require withholding (verify external success before committing APPLIED) or compensation (follow-up/withdraw). An evidence-loop retry of an emission risks double-application.
   - Commit-to-DB only after external confirmation (withholding = output-commit discipline): don't mark APPLIED on click; mark on verified site confirmation.
2. **Capability set known before load → approval at load time, not discovery time** (paper §6.3) — statically collect the applicator's full action plan (sites, fields, credentials, risk) and present the WHOLE emission set in the HITL approval, instead of per-action discovery. Makes approval decisions informed and cheap.
3. **Reactive dependency activation** (Koishi case study) — a component whose dependency is unavailable stays INACTIVE until it appears, without erroring. FlowJob: missing browser/DISPLAY/credentials should keep a job pending (dormant) rather than UNFIXABLE; when a dependency changes (model switch, browser update), reactivate only the affected dependents, not everything. Settings edits in the TUI = config reconciliation: re-init only what the change touches (model → LLM client; db path → store), no full restart (HMR idea, §5.2.2).
4. **Session log as source of truth, derived state, replay** (invariant.ts, surface.ts) — append-only interaction log; derive spend/state by fold (already done in spirit). Upgrade: replay mode — run the pipeline against a recorded interaction log instead of a live model (dsh's llm-replay). Stronger than fake agents for tests, and gives crash-recovery from the log alone.
5. **Live-session check before acting** (invariant.ts) — operations verify their session is still alive before resuming (pause/resume, wait_fn): after a pause or dependency change, don't continue a job on a stale session.
6. **Interception on the context, not in component code** (paper §6.3) — central write-policy for sensitive data: redaction of PII/keys applied at the interaction-store boundary, adjustable without touching agents. Central place = one audit point.
7. **Risk ladder + fail-closed escalation, approval BEFORE execution** (sandbox/escalation.ts) — FlowJob action risk ladder: read/navigate (safe) → fill form (workspace-write) → submit/send (danger, requires approval). Precompute the ask; deny by default.
8. **Effect registry with ordered withdrawal** (paper §3.1) — register effects at creation (browser, watcher, notification subscription) with inverses; teardown = ordered LIFO withdrawal (pause notifications last, browser before watcher). Formalizes what stop() methods do ad hoc.

## Open questions / gaps (not checked)

- Actual session.ts `deriveMessages` implementation and `step/start` event shapes (only the invariant file read).
- llm-replay replay-driven test harness details.
- Whether dsh uses HMR for hot-loading new tools in a live session (paper claims HMR in Cordis).
- Day-1 field reports mention UI lag / write-behind batching — unverified.