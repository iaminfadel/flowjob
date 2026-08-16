"""LLM provider registry, request logging, and failover helpers.

- Reads providers from flowjob.yaml (`llm.providers`) and .env keys.
- Every LLM call site logs a full request/response record to SQLite
  (table `llminteraction`) for auditing and cost tracking.
- On failure, callers can fall back to the next provider in priority order.
"""
from __future__ import annotations

import os
import time
import json
from pathlib import Path
from typing import Any, Optional, Callable

from langchain_openai import ChatOpenAI
from sqlmodel import Session

from src.config import load_config
from src.db.store import init_db


class Provider:
    """One OpenAI-compatible LLM endpoint."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str, priority: int = 1):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.priority = priority

    def __repr__(self) -> str:
        return f"Provider({self.name}, model={self.model})"


_DEFAULT_PROVIDERS = [
    ("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "qwen/qwen3.8-27b", 1),
    ("orca", "https://api.orcarouter.ai/v1", "ORCAROUTER_API_KEY", "orcarouter/free", 2),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "gemini-flash-latest", 3),
]


def has_provider_keys() -> bool:
    """True if any provider API key is present in the raw environment (no .env loading)."""
    return any(os.environ.get(k) for k in ("OPENROUTER_API_KEY", "ORCAROUTER_API_KEY", "GEMINI_API_KEY"))


def load_providers() -> list[Provider]:
    """Resolve the provider chain from flowjob.yaml + environment keys."""
    providers: list[Provider] = []

    try:
        cfg = load_config("flowjob.yaml")
        raw = getattr(cfg.llm, "providers", None) or []
    except Exception:
        raw = []

    if raw:
        for i, entry in enumerate(raw):
            name = entry.get("name", "")
            base_url = entry.get("base_url", "")
            api_key = os.environ.get(entry.get("api_key_env", ""), "")
            model = entry.get("model", "")
            if name and base_url and api_key and model:
                providers.append(Provider(name, base_url, api_key, model, priority=entry.get("priority", i + 1)))
    else:
        for name, base_url, env_key, model, priority in _DEFAULT_PROVIDERS:
            api_key = os.environ.get(env_key, "")
            if api_key:
                providers.append(Provider(name, base_url, api_key, model, priority))

    providers.sort(key=lambda p: p.priority)
    return providers


def create_chat(provider: Provider, model: Optional[str] = None, temperature: float = 0.2, max_tokens: Optional[int] = None, extra_body: Optional[dict] = None) -> ChatOpenAI:
    """Build a ChatOpenAI client for a provider, preferring its own model."""
    kwargs: dict[str, Any] = {
        "model": model or provider.model,
        "api_key": provider.api_key,
        "base_url": provider.base_url,
        "temperature": temperature,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if extra_body:
        kwargs["extra_body"] = extra_body
    return ChatOpenAI(**kwargs)


_SESSION_PROVIDER_HINTS = ("openrouter.ai", "orcarouter.ai")


def session_extra_body(provider: Provider, job_id: str = "") -> Optional[dict]:
    """OpenRouter-style sticky-routing session pin for one job's calls.

    OpenRouter uses `session_id` as its sticky-routing key so every call for
    the same job lands on the same provider endpoint that holds the warm
    prompt cache (cache reads cost 0.1-0.25x input). Gemini's OpenAI-compat
    endpoint rejects unknown body fields, so it is excluded.
    """
    if not job_id:
        return None
    base = (provider.base_url or "").lower()
    if not any(hint in base for hint in _SESSION_PROVIDER_HINTS):
        return None
    return {"session_id": job_id}


# ---------------------------------------------------------------------------
# Dead-provider tracking: providers that fail hard once are skipped for the
# rest of the process lifetime, so a dead endpoint doesn't burn time on
# every subsequent call (402 credits-out, daily quota 429s, etc.).
# ---------------------------------------------------------------------------
_failure_state: dict[str, float] = {}


def mark_provider_failure(provider: Provider) -> None:
    _failure_state[provider.name] = time.time()


def order_providers(providers: list[Provider]) -> list[Provider]:
    """Healthy providers first; failed providers (still warm) skipped."""
    live = [p for p in providers if p.name not in _failure_state]
    if live:
        return live
    return sorted(providers, key=lambda p: -_failure_state.get(p.name, 0.0))


_engine_cache: dict[str, Any] = {}


def _engine(db_path: str = "flowjob.db"):
    """Cached engine so logging is cheap and reuses one connection pool."""
    if db_path not in _engine_cache:
        _engine_cache[db_path] = init_db(db_path)
    return _engine_cache[db_path]


def log_interaction(
    *,
    agent_name: str,
    prompt: str,
    response: str = "",
    extracted: Optional[dict] = None,
    provider: str = "",
    model: str = "",
    job_id: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
    cost_usd: float = 0.0,
    latency_ms: int = 0,
    success: bool = True,
    error: str = "",
    db_path: str = "flowjob.db",
) -> int:
    """Persist one LLM interaction to SQLite. Returns record id (0 on failure)."""
    from src.db.models import LLMInteraction

    try:
        engine = _engine(db_path)
        record = LLMInteraction(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            agent_name=agent_name,
            job_id=job_id or "",
            provider=provider,
            model=model,
            prompt=prompt[:200_000],
            response=response[:200_000],
            extracted=extracted or {},
            prompt_tokens=int(prompt_tokens or 0),
            completion_tokens=int(completion_tokens or 0),
            cached_tokens=int(cached_tokens or 0),
            cost_usd=float(cost_usd or 0.0),
            latency_ms=int(latency_ms or 0),
            success=bool(success),
            error=error[:20_000],
        )
        with Session(engine) as session:
            session.add(record)
            session.commit()
            return record.id
    except Exception:
        return 0


def serialize_messages(messages: Any) -> str:
    """Best-effort serialization of prompt messages to plain text for the log."""
    try:
        if isinstance(messages, str):
            return messages
        if isinstance(messages, (list, tuple)):
            parts = []
            for m in messages:
                if isinstance(m, str):
                    parts.append(m)
                elif hasattr(m, "content"):
                    parts.append(getattr(m, "content", "") or "")
                else:
                    parts.append(str(m))
            return "\n\n".join(parts)
        if hasattr(messages, "content"):
            return getattr(messages, "content", "") or ""
        return str(messages)
    except Exception:
        return str(messages)


def _usage_info(response: Any) -> dict:
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        usage = {}
    prompt_tokens = int(usage.get("input_tokens", 0) or 0)
    completion_tokens = int(usage.get("output_tokens", 0) or 0)

    cached_tokens = 0
    details = usage.get("input_token_details")
    if isinstance(details, dict):
        cached_tokens = int(details.get("cache_read", 0) or 0)
    cost_usd = 0.0
    try:
        cost_usd = float(usage.get("total_cost", 0.0) or 0.0)
    except (AttributeError, TypeError, ValueError):
        pass
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "cost_usd": cost_usd,
    }


def response_text(response: Any) -> str:
    """Extract human-readable text + tool calls from a LangChain response."""
    parts = []
    content = getattr(response, "content", None)
    if content:
        parts.append(content if isinstance(content, str) else json.dumps(content, default=str))
    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        parts.append(json.dumps(tool_calls, default=str))
    return "\n".join(p for p in parts if p)


def invoke_llm(
    llm: ChatOpenAI,
    messages: list,
    *,
    agent_name: str = "",
    job_id: str = "",
    provider: str = "",
    model: str = "",
    on_response: Optional[Callable[[Any], None]] = None,
    db_path: str = "flowjob.db",
) -> Any:
    """Invoke an LLM and persist the full request/response. Raises on error."""
    start = time.time()
    prompt_text = serialize_messages(messages)
    try:
        response = llm.invoke(messages)
        latency_ms = int((time.time() - start) * 1000)
        usage = _usage_info(response)
        log_interaction(
            agent_name=agent_name,
            job_id=job_id,
            provider=provider or "",
            model=model or getattr(llm, "model_name", ""),
            prompt=prompt_text,
            response=response_text(response),
            latency_ms=latency_ms,
            success=True,
            **usage,
            db_path=db_path,
        )
        if on_response:
            on_response(response)
        return response
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        log_interaction(
            agent_name=agent_name,
            job_id=job_id,
            provider=provider or "",
            model=model or getattr(llm, "model_name", ""),
            prompt=prompt_text,
            latency_ms=latency_ms,
            success=False,
            error=f"{type(e).__name__}: {e}",
            db_path=db_path,
        )
        raise