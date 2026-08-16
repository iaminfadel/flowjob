# Research: Schema-as-Final-Tool Loop vs the Live OrcaRouter Endpoint (`qwen/qwen3.8-27b-free`)

> Live verification (real invocations, 2026-08-16) of the writer's tool-calling design from `design_spec.md` §10.4 — "one LLM invocation per round: 0..n `edit_resume` calls, optionally `request_human_input`, always `emit_plan` last" — against the project's configured endpoint. Follows up `research/openrouter_langchain_compatibility.md`, which concluded (for OpenRouter + Gemini 2.x) that `with_structured_output` + tools together 400, and that the fix is a schema-as-final-tool loop. This doc tests that loop against the live endpoint the project now points at.

## Environment & Prerequisites

- **Project deps**: `langchain-core 1.5.5`, `langchain-openai 1.5.1`, `pydantic 2.13.4` (installed in the venv; run via `uv run python`).
- **API key**: `OPENROUTER_API_KEY` in `.env` (prefix `sk-orca-…`).
- All probe scripts were throwaway, under `/tmp/opencode/flowjob_probe/` (nothing written into the repo).

## Primary Sources & Documentation

- **OrcaRouter homepage** (base_url, key format, model list): [https://orcarouter.com](https://orcarouter.com)
- **OrcaRouter live model card** for `qwen/qwen3.8-27b-free` via `GET /v1/models` on `api.orcarouter.ai` (context 262,144; free tier; claims "native tool calling, structured outputs").
- **OpenRouter Structured Outputs (`response_format`)**: [https://openrouter.ai/docs/structured-outputs](https://openrouter.ai/docs/structured-outputs)
- **OpenRouter Tools & Function Calling**: [https://openrouter.ai/docs/tools](https://openrouter.ai/docs/tools)
- **LangChain OpenAI Integration (`ChatOpenAI`)**: [https://python.langchain.com/docs/integrations/chat/openai/](https://python.langchain.com/docs/integrations/chat/openai/)
- **LangChain Structured Output guide**: [https://python.langchain.com/docs/how_to/structured_output/](https://python.langchain.com/docs/how_to/structured_output/)
- Prior work: `research/openrouter_langchain_compatibility.md`.

---

## 0. ⚠️ Environment finding: the configured base_url is dead DNS

**`https://api.orcarouter.com/v1` does not exist.** Every resolver queried (systemd-resolved stub, `1.1.1.1`, `8.8.8.8`, and the authoritative Cloudflare nameservers `hugh/sue.ns.cloudflare.com`) returns **NXDOMAIN / zero records** (no A, AAAA, CNAME, TXT) for `api.orcarouter.com`. `curl` fails with `Could not resolve host`.

The live gateway is **`https://api.orcarouter.ai/v1`** (resolves to `43.169.27.119`, returns `HTTP 200` for authenticated calls). The official OrcaRouter homepage documents exactly this:

```python
client = OpenAI(
    base_url="https://api.orcarouter.ai/v1",
    api_key=ORCAROUTER_API_KEY,   # sk-orca-…
)
```

Source: [https://orcarouter.com](https://orcarouter.com) (hero snippet, "Get your API key", and pricing sections). `flowjob.yaml` currently points at the dead `.com` host:

```yaml
llm:
  openrouter_base_url: "https://api.orcarouter.com/v1"   # ← NXDOMAIN, fix to .ai
```

**All probes below ran against `https://api.orcarouter.ai/v1`** with the same key and same model id.

---

## 1. Probe results (summary)

| # | Probe | Result |
|---|-------|--------|
| 1 | `ChatOpenAI` basic call on the endpoint | ✅ **PASS** |
| 2 | `.bind_tools([...])`, prompt that must use a tool | ✅ **PASS** (real `tool_calls` returned) |
| 3 | `with_structured_output(Schema)` | ❌ **FAIL** (all three methods) |
| 4 | `with_structured_output` + tools on same llm | ❌ **FAIL** (no 400, but broken — see 4) |
| 5 | Schema-as-final-tool loop (`edit_resume` + `request_human_input` + `emit_plan`) | ✅ **PASS** |
| 6 | Token/model quirks | ⚠️ **Mixed** (see 6) |

---

## 1. Probe 1 — basic `ChatOpenAI` call — ✅ PASS

```python
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

llm = ChatOpenAI(
    model="qwen/qwen3.8-27b-free",
    api_key=SecretStr(key),                     # from .env
    base_url="https://api.orcarouter.ai/v1",
    temperature=0,
    max_tokens=512,
)
out = llm.invoke("Reply with exactly: PONG")
# out.content == "\n\nPONG"; finish_reason == "stop"
```

---

## 2. Probe 2 — `.bind_tools` — ✅ PASS

```python
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather in a city."""
    return f"sunny, 27C in {city}"

llm_with_tools = llm.bind_tools([get_weather, multiply])

out = llm_with_tools.invoke("What is the weather in Cairo right now?")
# out.content == ""
# out.tool_calls == [{'name': 'get_weather', 'args': {'city': 'Cairo'}, 'id': 'chatcmpl-tool-…', 'type': 'tool_call'}]
# out.response_metadata['finish_reason'] == "tool_calls"
```

Tool calling works with `langchain_openai.ChatOpenAI` on this endpoint exactly as the prior OpenRouter research claimed.

---

## 3. Probe 3 — `with_structured_output(Schema)` — ❌ FAIL (all methods)

Tested all three LangChain methods on the **free** model with a simple `CoverageReport` schema:

| method | transport | result |
|---|---|---|
| `function_calling` | sends `tools` + **forced `tool_choice`** | **503 `upstream_unavailable`** (reproducible 5/5) |
| `json_schema` | sends `response_format={"type":"json_schema",…}` | 200, but output is **prose-wrapped JSON** (`**Evaluation{…}`) → `pydantic.ValidationError: json_invalid` |
| `json_mode` | sends `response_format={"type":"json_object"}` | 200, prose-wrapped → `OutputParserException` |

```python
# function_calling → openai.InternalServerError: 503
# {'error': {'code': 'upstream_unavailable',
#   'message': 'The upstream provider is temporarily unavailable. Please try again later.'}}
```

Cause split in Probe 6: the **forced `tool_choice`** (used by `method="function_calling"`) 503s at the upstream provider for this model. And the free model **ignores `response_format`** (no constrained decoding), so `json_schema`/`json_mode` return unparsable text. **On `qwen/qwen3.8-27b-free`, none of the three `with_structured_output` methods work.**

---

## 4. Probe 4 — `with_structured_output` + tools on the same llm — ❌ FAIL

Prior research predicted a 400 from `response_format` + `tools` together (observed on Gemini 2.x via OpenRouter). **That 400 does NOT reproduce on this endpoint** — the gateway accepts both together (HTTP 200) — but the combination is still unusable:

| combination | result |
|---|---|
| `.bind_tools([…]).with_structured_output(S, method="function_calling")` | 503 (forced tool_choice) |
| `.bind_tools([…]).with_structured_output(S, method="json_schema")` | 200, but schema not enforced: **1/5** calls parse; 4/5 return `**Evaluation{…}` prose-wrap → `json_invalid` |
| `.bind_tools([…]).with_structured_output(S, method="json_mode")` | 200, valid JSON but the model invents its own keys → schema mismatch → `OutputParserException` |

Raw payload check (no LangChain) for `response_format` + `tools` together on the free model: HTTP 200, and the model replied by writing a literal `<tool_call>…` XML block into `content` instead of an actual tool call — the endpoint simply does not honor the constraint.

**Verdict for this probe**: on `qwen/qwen3.8-27b-free`, structured output and tool calling cannot be mixed through `with_structured_output` in any method. The schema-as-final-tool workaround is *required*, not optional — matching the prior research's conclusion, though via a different failure mode (no 400; instead 503 + unenforced schema).

---

## 5. Probe 5 — the schema-as-final-tool loop — ✅ PASS

The design's exact mechanism: bind `edit_resume` + `request_human_input` **plus** an `emit_plan` tool whose `parameters` are the pydantic `EmitPlan` schema; instruct the model to finish every round with `emit_plan`; parse the final tool-call's args. **Never** force `tool_choice`. Working snippet:

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

@tool
def edit_resume(target: str, op: str, section: str, index: int, tag: str, content: str) -> str:
    """Edit the resume draft. target is 'draft' or 'bank'. op is 'add', 'replace' or 'remove'. …"""
    return f"applied {op} to {target}/{section}[{index}]"

@tool
def request_human_input(question: str, context: str) -> str:
    """Ask the human for information that cannot be derived from the resume draft."""
    return f"human asked: {question}"

class EmitPlan(BaseModel):
    edits: list[dict]        # edit_resume call dicts made this round
    remaining: list[str]     # requirement ids still unaddressed
    needs_human: bool
    summary: str

emit_tool = {
    "type": "function",
    "function": {
        "name": "emit_plan",
        "description": "Emit the final plan for this round. ALWAYS the last tool call of the round.",
        "parameters": EmitPlan.model_json_schema(),   # ← schema-as-a-tool
    },
}

llm_with_tools = llm.bind_tools([edit_resume, request_human_input, emit_tool])
```

Round-loop mechanics (orchestrator side):

```python
for rnd in range(max_rounds):
    out = llm_with_tools.invoke(messages)
    names = [tc["name"] for tc in out.tool_calls]
    for tc in out.tool_calls:
        if tc["name"] == "emit_plan":
            plan = EmitPlan.model_validate(tc["args"])   # ← parseable emit_plan
            return plan                                   # round complete
        fn = edit_resume if tc["name"] == "edit_resume" else request_human_input
        messages.append({"role": "tool", "tool_call_id": tc["id"],
                         "content": fn.invoke(tc["args"])})  # execute locally
```

**Live result** (tiny fake resume-draft prompt):

- **Round 0**: `finish_reason=tool_calls` with `edit_resume(target="draft", op="add", section="experience", index=1, tag="R1", content="5+ years of Python …")` **and** `request_human_input(question=…, context=…)` in the same message. No `emit_plan` on the first shot.
- **Round 1** (after the two tool results were fed back): model emitted a single `emit_plan` call, args parsed cleanly:

```python
EmitPlan(edits=[{'target': 'draft', 'op': 'add', 'section': 'experience',
                 'index': 1, 'tag': 'R1', 'content': '5+ years of Python …'}],
         remaining=['R2'], needs_human=True,
         summary='Added quantified 5+ years Python bullet for R1; asked human …')
```

**The loop works on this endpoint as-is.** The real `edit_resume` calls and `request_human_input` are emitted as genuine tool calls, and the final `emit_plan` tool-call args parse directly into the pydantic model with **zero** `response_format`/`tool_choice` involvement.

### One adaptation the orchestrator must make

The model does **not reliably** put `emit_plan` in the *first* response of a round (it calls the edit tools and stops, `finish_reason=tool_calls`, no `emit_plan`). Observed in both the probe and every reliability run before the rate limit hit. The design text says "one LLM invocation per round: … always `emit_plan` last" — in practice a round may need **2 invocations**: (1) edit tools, (2) after feeding tool results, the model emits `emit_plan` (and nothing else). Orchestrate as:

```
if "emit_plan" in tool_calls:   → parse, round complete
elif tool_calls non-empty:      → execute tools, append tool messages, re-invoke  (loop continues)
else:                           → prompt "you did not call emit_plan"
```

Do **not** try to force the last call with `tool_choice` — see Probe 6.

---

## 6. Probe 6 — token/model quirks — ⚠️ MIXED

### 6a. Forced `tool_choice` is unsupported → 503

Raw `tool_choice` mapping, confirmed on **paid** `qwen/qwen3.8-27b` (same arch, not rate-limited) — the free model 503'd identically on forced choice earlier:

| `tool_choice` | result |
|---|---|
| *(omitted)* | ✅ OK, model may call tools |
| `"auto"` | ✅ OK, model may call tools |
| `"none"` | ✅ OK, no tool calls |
| `"required"` | ❌ **503 `upstream_unavailable`** |
| `{"type":"function","function":{"name":…}}` | ❌ **503 `upstream_unavailable`** |

This is **not** a free-tier capacity issue — the paid sibling fails the same way. The self-hosted Qwen3.8 27B upstream rejects any forced tool selection. Because LangChain's `method="function_calling"` sets a forced `tool_choice` (Probe 3/4), it is unusable on this model.

### 6b. Free model ignores `response_format`; paid model honors it

- **`qwen/qwen3.8-27b-free`**: `response_format={"type":"json_schema","json_schema":{…strict…}}` returns HTTP 200 but unconstrained prose-wrapped JSON (`**Evaluation{…}`) — **no constrained decoding on the free tier**.
- **`qwen/qwen3.8-27b` (paid)**: identical request returns clean JSON — `{"city": "Cairo", "temp_c": 31}`. Structured output works on the paid sibling.

### 6c. `strict` / `required`

- Tool `parameters.required` arrays are honored (all `edit_resume`/`emit_plan` fields came back complete).
- `json_schema.strict=true` + `additionalProperties:false` is accepted (no 400) but only enforced on the paid model.

### 6d. Free-tier rate limiting (operational showstopper)

After ~10–15 requests in this session, the free model began returning:

```json
{"error": {"code": "free_rate_limited",
  "message": "free model capacity is limited right now — upgrade or top up …",
  "type": "orcarouter_api_error"}}
```

with **`retry-after: 33584`** (≈ **9.3 hours**). The `-free` model is burst-limited and can be unavailable for the better part of a day. A multi-round writer loop (2+ invocations per round) will trip this constantly.

### 6e. Other parameters

- `max_tokens` 512–1500 verified; model card exposes `context_length: 262144` and `max_completion_tokens: 0` (no separate published cap; OpenAI-style `max_tokens` is the accepted param — use `max_completion_tokens` only if the gateway asks for it; it errored with `free_rate_limited` before we could distinguish, so treat as unverified).
- `temperature=0` works. Endpoint types from the live model card: `["openai", "openai-response"]` — the standard Chat Completions path is supported.
- `qwen/qwen3.8-27b-free` supports **parallel tool calls in one message** (round 0 emitted `edit_resume` + `request_human_input` together).

---

## Compatibility matrix (live endpoint, `api.orcarouter.ai/v1`)

| Capability | `qwen/qwen3.8-27b-free` | `qwen/qwen3.8-27b` (paid) |
|---|---|---|
| Basic chat (OpenAI SDK / ChatOpenAI) | ✅ | ✅ |
| `.bind_tools` + natural tool calls | ✅ | ✅ |
| `tool_choice: "auto" / "none"` | ✅ | ✅ |
| `tool_choice: "required"` / named | ❌ 503 | ❌ 503 |
| `response_format` json_schema (constrained) | ❌ ignored (prose-wrapped) | ✅ enforced |
| `with_structured_output(method="function_calling")` | ❌ 503 | ❌ 503 |
| `with_structured_output(method="json_schema")` | ❌ parse-fail | ✅ (needs schema match) |
| `with_structured_output` + tools (any method) | ❌ | ⚠️ json_schema OK, rest broken |
| Schema-as-final-tool loop | ✅ | ✅ |
| Rate limit | 429 after ~10–15 calls, `retry-after` up to ~9.3 h | not observed in this session |

---

## Verdict

**The writer's schema-as-final-tool design works against the live endpoint as-is** — probe 5 proved the full cycle (`edit_resume` + `request_human_input` as real tool calls, `emit_plan` as the final call, args parsed into the pydantic plan). It is in fact the *only* reliable structured-output mechanism on this model, because:

1. forced `tool_choice` (used by `method="function_calling"`) 503s at the upstream for **both** free and paid, and
2. the free model ignores `response_format` entirely.

**What must change (besides the dead `.com` base_url):**

1. `flowjob.yaml` → `openrouter_base_url: "https://api.orcarouter.ai/v1"`.
2. The orchestrator's "one invocation per round" must tolerate a **two-invocation round**: if a response has edit tool calls but no `emit_plan`, feed the tool results back and re-invoke (the model then emits only `emit_plan`). Never attempt to force the final call.
3. Consider the **paid** `qwen/qwen3.8-27b` (or another model) for production: the free tier's ~9-hour burst lockout makes the multi-invocation writer loop, critic, and auditor impractical at any scale.

## Consequences for the critic / auditor (`with_structured_output`)

`src/agents/structured_llm.py:30` currently builds `self.llm.with_structured_output(self.response_schema, method="function_calling")`. **On `qwen/qwen3.8-27b-free` this will 503 every call.** The critic and the hygiene auditor are read-only and don't need real tools, so the smallest change is to drop the `function_calling` method:

- **Free model**: `method="json_schema"` still fails to parse (schema unenforced, prose-wrapped JSON). Options: (a) a prose-stripping + retry parser around `json_schema` output, or (b) reuse the schema-as-final-tool pattern — bind the report schema as a single tool, prompt "return the report as a tool call, do not call any other tool", and parse the (only) tool-call args. Option (b) is deterministic and identical to the writer's proven loop, so it is the recommended shared mechanism.
- **Paid model**: `method="json_schema"` works cleanly and is the simplest choice.

Either way the current `method="function_calling"` default is a guaranteed 503 on this model family.

## Consequences for `request_human_input` as a tool

No change needed — probe 5 verified the model calls it with the exact `(question, context)` signature, in the same round as `edit_resume`, and only when instructed (the prompt's R2 "cannot verify" trigger produced the call). It coexists fine with the `emit_plan` final-call pattern.

---

## Appendix — failure-mode table for the record

| Scenario | HTTP / exception | notes |
|---|---|---|
| `api.orcarouter.com/v1` (configured base_url) | DNS NXDOMAIN | wrong TLD; use `.ai` |
| basic chat, tools, natural tool calls | 200 | works |
| forced `tool_choice` (any form) | 503 `upstream_unavailable` | upstream limitation, free + paid |
| `response_format` on free model | 200 + unenforced | prose-wrapped JSON, parse fails |
| `response_format` on paid model | 200 + enforced | clean JSON |
| free-model burst | 429 `free_rate_limited`, `retry-after: 33584` | ~9.3 h lockout |
| `with_structured_output(fc)` | 503 (probe 3/4) | LangChain forces tool_choice |
| schema-as-final-tool loop | 200, parsed | the working path (probe 5) |
