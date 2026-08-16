# Research: OpenRouter & LangChain `ChatOpenAI` Compatibility & Structured Outputs

> Research into configuring `langchain_openai.ChatOpenAI` with OpenRouter, API key handling, app attribution headers, and `with_structured_output()` behavior with Pydantic v2 models across OpenRouter model providers.

## Primary Sources & Documentation

All findings derived directly from primary official documentation:
- **OpenRouter API Overview**: [https://openrouter.ai/docs](https://openrouter.ai/docs)
- **OpenRouter App Attribution Headers**: [https://openrouter.ai/docs/app-attribution](https://openrouter.ai/docs/app-attribution)
- **OpenRouter Structured Outputs (`response_format`)**: [https://openrouter.ai/docs/structured-outputs](https://openrouter.ai/docs/structured-outputs)
- **OpenRouter Tools & Function Calling**: [https://openrouter.ai/docs/tools](https://openrouter.ai/docs/tools)
- **LangChain OpenAI Integration (`ChatOpenAI`)**: [https://python.langchain.com/docs/integrations/chat/openai/](https://python.langchain.com/docs/integrations/chat/openai/)
- **LangChain Structured Output Guide**: [https://python.langchain.com/docs/how_to/structured_output/](https://python.langchain.com/docs/how_to/structured_output/)
- **LangChain OpenRouter Integration (`ChatOpenRouter`)**: [https://python.langchain.com/docs/integrations/chat/openrouter/](https://python.langchain.com/docs/integrations/chat/openrouter/)

---

## 1. ChatOpenAI Configuration for OpenRouter

To use OpenRouter endpoints with standard `langchain_openai.ChatOpenAI`, configure `base_url`, API key, and attribution headers as follows:

```python
import os
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

# Option A: Passing OPENROUTER_API_KEY explicitly
llm = ChatOpenAI(
    model="anthropic/claude-3.5-sonnet",
    base_url="https://openrouter.ai/api/v1",
    api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
    default_headers={
        "HTTP-Referer": "https://github.com/iaminfadel/flowjob",  # App URL for rankings
        "X-Title": "FlowJob Agent Pipeline",                    # App Title on leaderboard
    },
    temperature=0,
)
```

### Key Configuration Findings

1. **`base_url` / `openai_api_base`**:
   - Must be set to `https://openrouter.ai/api/v1`.
   - In `langchain_openai>=0.1.0`, `base_url` is the standard parameter name (`openai_api_base` is accepted as an alias for backwards compatibility).

2. **API Key Resolution (`OPENROUTER_API_KEY`)**:
   - `ChatOpenAI` from `langchain_openai` defaults to inspecting `os.environ["OPENAI_API_KEY"]`. It does **not** automatically inspect `OPENROUTER_API_KEY`.
   - To use `OPENROUTER_API_KEY` without code changes, set `OPENAI_API_KEY` in environment: `export OPENAI_API_KEY="$OPENROUTER_API_KEY"`.
   - Alternatively, explicitly pass `api_key=os.environ.get("OPENROUTER_API_KEY")` or `api_key=SecretStr(...)` during instantiation.
   - Note: The dedicated `langchain-openrouter` package (`ChatOpenRouter`) automatically checks `OPENROUTER_API_KEY`.

3. **App Attribution Headers (`HTTP-Referer` and `X-Title`)**:
   - OpenRouter uses attribution headers to track application usage and calculate public leaderboard rankings.
   - `HTTP-Referer` (required for rankings): Unique site or repository URL.
   - `X-Title` / `X-OpenRouter-Title` (optional): Human-readable app name shown on OpenRouter dashboard.
   - Passed via `default_headers={ "HTTP-Referer": "...", "X-Title": "..." }`.
   - Caching Note: Attribution headers are excluded from OpenRouter prompt cache keys; adding or updating them does not trigger cache misses.

4. **Provider Preferences & Extra Parameters**:
   - OpenRouter-specific controls (e.g., provider routing order, fallbacks) can be passed via `extra_body` in `model_kwargs`:
     ```python
     llm = ChatOpenAI(
         model="anthropic/claude-3.5-sonnet",
         base_url="https://openrouter.ai/api/v1",
         api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
         extra_body={
             "provider": {
                 "order": ["Anthropic", "AWS Bedrock"],
                 "allow_fallbacks": True
             }
         }
     )
     ```

---

## 2. `with_structured_output()` Mechanics with Pydantic v2

When calling `llm.with_structured_output(Schema)` on `ChatOpenAI`:

1. **Schema Generation**: LangChain extracts the JSON schema from the Pydantic v2 `BaseModel` via `model_json_schema()`.
2. **Request Formatting**: LangChain injects the schema into the request using the specified `method`:
   - `method="function_calling"` (Default when binding tools): Sends `tools=[{"type": "function", "function": {...}}]` and `tool_choice`.
   - `method="json_schema"`: Sends `response_format={"type": "json_schema", "json_schema": {"name": "...", "schema": ..., "strict": True}}`.
   - `method="json_mode"`: Sends `response_format={"type": "json_object"}` with system prompt instructions.
3. **Response Parsing & Validation**: Upon receiving JSON from LLM, LangChain validates the payload via Pydantic v2 `model_validate_json()`.

### Pydantic v2 Features & Constraints

- **Field Descriptions**: `Field(description="...")` annotations are preserved in the JSON schema and guide LLM generation accuracy.
- **Strict Mode (`strict=True`)**:
  - Sets `additionalProperties: false` on the root object schema.
  - Requires all fields to be listed in `required`.
  - **Constraint**: Fields cannot contain default values (e.g., `field: str = "default"`) when `strict=True` is passed to `with_structured_output()`.

---

## 3. Model & Provider Compatibility Matrix on OpenRouter

| Model ID | Recommended Method | `function_calling` | `json_schema` | `json_mode` | Key Behaviors & Known Issues |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`openai/gpt-4o-mini`** | `json_schema` or `function_calling` | ✅ Excellent | ✅ Native | ✅ Supported | Native OpenAI constrained decoding via OpenRouter. 100% reliable for Pydantic v2 models. |
| **`anthropic/claude-3.5-sonnet`** | `function_calling` | ✅ Excellent | ⚠️ Emulated | ✅ Supported | OpenRouter maps OpenAI function schemas to Claude `tools` API seamlessly. `function_calling` is highly reliable. |
| **`google/gemini-2.5-pro`** | `function_calling` | ✅ Supported | ⚠️ Variable | ✅ Supported | OpenRouter translates tool calls. `json_schema` maps to Gemini `response_schema`. Nested `$defs` from Pydantic v2 may require flat schemas. |

### Model Breakdown & Analysis

#### 1. `openai/gpt-4o-mini`
- **Behavior**: Direct native OpenAI implementation.
- **Structured Output**: Native constrained decoding works out of the box with both `method="json_schema"` and `method="function_calling"`.
- **Pydantic v2 Support**: Handles nested models (`$defs`), unions, optional fields, and `strict=True` without schema transformation issues.

#### 2. `anthropic/claude-3.5-sonnet`
- **Behavior**: Proxied via OpenRouter translation layer.
- **Structured Output**: OpenRouter translates OpenAI tool definitions (`tools`) to Anthropic's native `tools` format. `method="function_calling"` works flawlessly.
- **Recommendation**: Use `method="function_calling"`. Avoid forcing `method="json_schema"` unless verified on the target provider endpoint.

#### 3. `google/gemini-2.5-pro`
- **Behavior**: Proxied via OpenRouter translation layer to Google Vertex/Gemini API.
- **Structured Output**: Supports tool calls and JSON schema (`response_mime_type: "application/json"` + `response_schema`).
- **Known Edge Cases**:
  - **Pydantic v2 `$defs` References**: Complex nested Pydantic models in v2 generate `$defs` references in JSON Schema. Gemini's schema parser can fail on `$defs` pointers.
  - **Workaround**: Use flat Pydantic models or use `method="function_calling"`.

---

## 4. Comparison: `ChatOpenAI` vs `ChatOpenRouter` (`langchain-openrouter`)

| Feature | `ChatOpenAI(base_url="...")` | `ChatOpenRouter` (`langchain-openrouter`) |
| :--- | :--- | :--- |
| **Dependency** | `langchain-openai` (standard) | `langchain-openrouter` (optional) |
| **Env Var Auto-Detection** | `OPENAI_API_KEY` (requires manual mapping) | `OPENROUTER_API_KEY` (automatic) |
| **App Attribution** | Pass in `default_headers` | Dedicated `app_url` and `app_title` kwargs |
| **Structured Output** | Standard `with_structured_output()` | Standard `with_structured_output()` |
| **Portability** | High (standard OpenAI SDK wrapper) | Dedicated OpenRouter integration |

---

## 5. Implementation Example

```python
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
import os

class TechnicalSummary(BaseModel):
    summary: str = Field(description="One-sentence executive summary")
    confidence_score: float = Field(description="Score between 0.0 and 1.0")
    key_technologies: list[str] = Field(description="List of technologies mentioned")

# Initialize ChatOpenAI for OpenRouter
llm = ChatOpenAI(
    model="anthropic/claude-3.5-sonnet",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    default_headers={
        "HTTP-Referer": "https://github.com/iaminfadel/flowjob",
        "X-Title": "FlowJob",
    },
    temperature=0,
)

# Bind Pydantic v2 model via function calling method for cross-provider stability
structured_llm = llm.with_structured_output(TechnicalSummary, method="function_calling")

result = structured_llm.invoke("FlowJob uses Python, LangChain, and OpenRouter to run autonomous job search agents.")
print(result)
```
