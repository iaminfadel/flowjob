from typing import Any, Type, Callable, List, Optional
import os
import json
from pydantic import BaseModel
from langchain_openai import ChatOpenAI as _RealChatOpenAI
from langchain_core.prompts import PromptTemplate
from src.agents.runner import AgentRunner
from src.agents.llm_factory import (
    Provider,
    load_providers,
    create_chat,
    invoke_llm,
    order_providers,
    mark_provider_failure,
    session_extra_body,
)

class LangChainStructuredAgent(AgentRunner):
    def __init__(self, prompt_template: str, response_schema: Type[BaseModel], temperature: float = 0.2, preprocessors: List[Callable] = None, model_name: str = "google/gemini-2.5-pro", openrouter_base_url: str = "https://openrouter.ai/api/v1", openrouter_api_key: str = None, providers: List[Provider] = None, agent_name: str = "", max_tokens: int = 4000):
        super().__init__()
        self.prompt_template = prompt_template
        self.response_schema = response_schema
        self.temperature = temperature
        self.preprocessors = preprocessors or []
        self.model_name = model_name
        self.agent_name = agent_name or type(self).__name__
        self.max_tokens = max_tokens
        self.openrouter_base_url = openrouter_base_url
        self.openrouter_api_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")

        # Provider chain for failover: explicit config wins, else resolve from flowjob.yaml + .env
        if providers:
            self.providers = providers
        elif openrouter_base_url != "https://openrouter.ai/api/v1":
            self.providers = [Provider("explicit", openrouter_base_url, self.openrouter_api_key, model_name)]
        else:
            self.providers = load_providers()
            if not self.providers:
                raise RuntimeError("No working LLM provider found. Check OPENROUTER_API_KEY / ORCAROUTER_API_KEY / GEMINI_API_KEY in .env or llm.providers in flowjob.yaml.")

        if not self.providers[0].api_key:
            raise RuntimeError("❌ LLM provider API key is missing or invalid. Please export OPENROUTER_API_KEY (or another provider key) in your shell or .env file before running flowjob.")

        self.llm = create_chat(self.providers[0], temperature=temperature, max_tokens=max_tokens)

    def run(self, context: dict, job_id: str = "", agent_name: str = "") -> BaseModel:
        # Run preprocessors
        for preprocessor in self.preprocessors:
            context = preprocessor(context)

        prompt = PromptTemplate.from_template(self.prompt_template)
        formatted_prompt = prompt.format(**context)

        name = agent_name or self.agent_name
        return invoke_with_schema_tool(
            self.llm,
            [formatted_prompt],
            self.response_schema,
            providers=self.providers,
            temperature=self.temperature,
            agent_name=name,
            job_id=job_id,
            max_tokens=self.max_tokens,
        )


class SchemaExtractionError(Exception):
    pass


def _parse_tool_call(schema: Type[BaseModel], response: Any) -> Optional[BaseModel]:
    """Extract and validate the schema payload from an LLM response."""
    tool_calls = getattr(response, "tool_calls", [])
    if not tool_calls:
        content = getattr(response, "content", "").strip()
        if content:
            clean = content
            if "```json" in clean:
                clean = clean.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in clean:
                clean = clean.split("```", 1)[1].split("```", 1)[0].strip()
            try:
                parsed = json.loads(clean)
                return schema.model_validate(parsed)
            except Exception:
                if "{" in clean and "}" in clean:
                    try:
                        sub = clean[clean.find("{"):clean.rfind("}")+1]
                        parsed = json.loads(sub)
                        return schema.model_validate(parsed)
                    except Exception:
                        pass
        raise SchemaExtractionError("Model returned text but failed to call the expected tool.")

    tool_call = next((call for call in tool_calls if call.get("name") == schema.__name__), None)
    if not tool_call:
        tool_call = tool_calls[0]

    args = tool_call.get("args", {})
    if isinstance(args, str):
        args = json.loads(args)
    return schema.model_validate(args)


def invoke_with_schema_tool(llm: Any, messages: list, schema: Type[BaseModel], retries: int = 3, providers: List[Provider] = None, temperature: float = 0.2, agent_name: str = "", job_id: str = "", max_tokens: int = 4000) -> BaseModel:
    """
    Wraps LLM invocation using the schema-as-a-single-tool pattern.
    - Never forces `tool_choice` to avoid upstream 503 errors.
    - Retries on validation or missing tool calls; fails over across providers.
    - Persists every request/response via the logging layer.
    """
    # Plain (mocked/legacy) llm path — no failover, no logging.
    if not providers:
        llm_with_tools = llm.bind_tools([schema])
        last_error = None
        for _ in range(retries):
            try:
                response = llm_with_tools.invoke(messages)
                return _parse_tool_call(schema, response)
            except Exception as e:
                last_error = e
        raise last_error

    # Real provider chain with failover + logging.
    last_error = None
    for provider in order_providers(providers):
        try:
            chat = create_chat(provider, temperature=temperature, max_tokens=max_tokens, extra_body=session_extra_body(provider, job_id))
            llm_with_tools = chat.bind_tools([schema])
            for attempt in range(retries):
                try:
                    if isinstance(chat, _RealChatOpenAI):
                        response = invoke_llm(
                            llm_with_tools,
                            messages,
                            agent_name=agent_name,
                            job_id=job_id,
                            provider=provider.name,
                            model=provider.model,
                        )
                    else:
                        # Mocked LLM in tests — plain invocation, no logging.
                        response = llm_with_tools.invoke(messages)
                    return _parse_tool_call(schema, response)
                except Exception as e:
                    last_error = e
                    if attempt < retries - 1:
                        print(f"[llm] {provider.name} attempt {attempt + 1} failed ({type(e).__name__}); retrying...")
                        continue
                    raise last_error
        except Exception as e:
            last_error = e
            mark_provider_failure(provider)
            print(f"[llm] Provider {provider.name} ({provider.model}) failed: {type(e).__name__}: {e}. Trying next provider...")

    raise last_error