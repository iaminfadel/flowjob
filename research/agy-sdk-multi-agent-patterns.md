# Research: AGY SDK Multi-Agent Coordination Patterns

> Resolves [#2](https://github.com/iaminfadel/flowjob/issues/2)

## Source

All findings from the Google Antigravity SDK's primary documentation:
- `references/architecture.md` — core concepts (Agent, Conversation, Connection)
- `examples/getting_started/subagents.md` — subagent delegation
- `examples/getting_started/custom_tool.md` — custom tools + ToolContext state
- `examples/getting_started/hooks.md` — lifecycle hooks
- `examples/getting_started/periodic_trigger.md` — triggers for watch mode
- `examples/getting_started/persona_config.md` — system instructions
- `examples/getting_started/structured_output.md` — Pydantic response schemas
- `references/error_handling.md` — error recovery hooks
- `references/built_in_tools.md` — available built-in tools

## Core Architecture

The SDK has three pillars:
- **Agent** — entry point. Handles config, tools, policies, hooks, triggers.
- **Conversation** — stateful session. Manages history, context, streaming.
- **Connection** — transport to backend (Gemini API, LiteRT, OpenAI-compatible).

## Subagent Delegation Model

- Subagents are **enabled by default** via `CapabilitiesConfig(enable_subagents=True)`.
- The parent agent uses the built-in `start_subagent` tool to spawn a subagent.
- Subagent output flows back to the parent agent automatically.
- **Key insight**: subagent delegation is prompt-driven. The Coordinator doesn't call a Python function to spawn agents — it's instructed via system prompt to delegate, and the SDK handles the mechanics.

```python
config = LocalAgentConfig(
    capabilities=types.CapabilitiesConfig(enable_subagents=True),
)
```

### Implications for FlowJob

The Coordinator agent's system prompt is the orchestration layer. It needs:
1. Clear instructions on when to spawn each sub-agent (Scout, Analyst, Tailor, Checker, Applicator).
2. Structured output schemas (Pydantic) for each stage to pass typed data between agents.
3. The Coordinator doesn't need to be a Python pipeline — the LLM itself orchestrates based on its instructions.

**Alternative**: We could also build the pipeline in Python code (calling `agent.chat()` sequentially for each stage), using AGY SDK agents as the individual processors rather than relying on the LLM to orchestrate. This gives us deterministic flow control.

## Custom Tools

- Defined as Python functions with docstrings. The agent calls them via function calling.
- `ToolContext` provides cross-turn state via `ctx.get_state()` / `ctx.set_state()`.
- Built-in tools include: `list_directory`, `view_file`, `create_file`, `edit_file`, `run_command`, `search_web`, `read_url_content`, `generate_image`.
- `run_command` is **denied by default** — needs a policy override.
- Custom tools can **override built-ins** by using the same name.

### FlowJob Custom Tools Needed

| Agent | Custom Tools |
|-------|-------------|
| **Scout** | `scrape_linkedin_jobs(search_url: str) -> list[JobPosting]` — Playwright-based |
| **Analyst** | `score_job_fit(jd: str, master_resume: str, preferences: dict) -> FitScore` |
| **Tailor** | `generate_cv_html(master_resume: str, jd_analysis: dict, template: str) -> str` |
| **Checker** | `score_ats_compatibility(cv_html: str, jd_keywords: list) -> ATSScore` |
| **Applicator** | `submit_easy_apply(job_url: str, cv_pdf_path: str) -> ApplicationResult` |
| **Logger** | `log_application(record: ApplicationRecord) -> None` |

## Hooks (Lifecycle Interception)

Available hooks:
- `on_session_start` / `on_session_end`
- `pre_turn` / `post_turn` — inspect/reject turns
- `pre_tool_call_decide` — approve/reject tool calls
- `post_tool_call` — observe tool results
- `on_tool_error` — error recovery with fallback values
- `on_interaction` — handle user interaction requests
- `on_compaction` — context compaction events

### FlowJob Hook Uses

- **Rate limiting**: `pre_tool_call_decide` on the Applicator's `submit_easy_apply` tool — enforce delay between applications.
- **Logging**: `post_tool_call` on submission — log every application attempt.
- **Error recovery**: `on_tool_error` — if LinkedIn throws a CAPTCHA or session expires, pause and alert.

## Triggers (Watch Mode)

The SDK has native trigger support:
- `every(seconds, callback)` — periodic timer trigger
- `on_file_change(path, callback)` — file system watcher
- Custom triggers via async functions with `TriggerContext`

### FlowJob Watch Mode

```python
from google.antigravity.triggers import every, TriggerContext

async def poll_for_jobs(ctx: TriggerContext):
    """Check LinkedIn for new job postings."""
    await ctx.send("Check for new job postings matching my filters.")

poll_trigger = every(3600, poll_for_jobs)  # Poll every hour

config = LocalAgentConfig(
    triggers=[poll_trigger],
    # ... other config
)
```

This is a natural fit — the trigger sends a message to the Coordinator agent, which then runs the full pipeline for any new jobs found.

## Structured Output (Pydantic Schemas)

- Pass `response_schema=MyPydanticModel` to `LocalAgentConfig`.
- Call `response.structured_output()` to get typed dict.

### FlowJob Data Models (as Pydantic)

```python
class JobPosting(BaseModel):
    url: str
    title: str
    company: str
    location: str
    posted_date: str
    jd_text: str

class FitScore(BaseModel):
    score: int  # 0-100
    matching_skills: list[str]
    missing_skills: list[str]
    recommendation: str  # "apply" | "skip" | "review"

class ATSScore(BaseModel):
    keyword_score: int  # 0-100
    format_score: int  # 0-100
    ai_recruiter_score: int  # 0-100
    overall: int  # 0-100
    feedback: str
    pass_threshold: bool
```

## Error Handling

- `AntigravityValidationError` — input validation failures
- `AntigravityConnectionError` — connection issues
- `FallbackHook` pattern — intercept tool errors and provide recovery guidance

## Recommended Architecture for FlowJob

**Hybrid approach**: Python-orchestrated pipeline using AGY SDK agents as processors.

```
┌─────────────────────────────────────────────────┐
│  Python Pipeline (deterministic flow control)    │
│                                                  │
│  1. Scout Agent → list[JobPosting]               │
│  2. For each job:                                │
│     a. Analyst Agent → FitScore                  │
│     b. If fit > threshold:                       │
│        i.  Tailor Agent → CV HTML                │
│        ii. Checker Agent → ATSScore              │
│        iii. If !pass: loop i-ii (max N times)    │
│        iv. Applicator Agent → submit             │
│        v.  Logger module → SQLite                │
│                                                  │
│  Watch mode: wrapped in AGY trigger (every N sec)│
└─────────────────────────────────────────────────┘
```

Each agent is a separate `Agent` instance with its own `LocalAgentConfig`, custom tools, and system prompt. The Python code orchestrates the pipeline — calling `agent.chat()` on each agent in sequence, passing structured data between them.

This is better than pure LLM orchestration because:
1. **Deterministic flow** — the pipeline always runs the same stages in the same order.
2. **Typed interfaces** — Pydantic schemas ensure data integrity between stages.
3. **Independent optimization** — each agent's prompt and tools can be tuned independently.
4. **Error isolation** — a failure in one stage doesn't corrupt the Coordinator's context.
5. **Testability** — each agent can be tested in isolation with mock inputs.
