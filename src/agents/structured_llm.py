from typing import Any, Type, Callable, List
import os
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from src.agents.runner import AgentRunner

class LangChainStructuredAgent(AgentRunner):
    def __init__(self, prompt_template: str, response_schema: Type[BaseModel], temperature: float = 0.2, preprocessors: List[Callable] = None, model_name: str = "google/gemini-2.5-pro", openrouter_base_url: str = "https://openrouter.ai/api/v1", openrouter_api_key: str = None):
        super().__init__()
        self.prompt_template = prompt_template
        self.response_schema = response_schema
        self.temperature = temperature
        self.preprocessors = preprocessors or []
        self.model_name = model_name
        self.openrouter_base_url = openrouter_base_url
        self.openrouter_api_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")

        if not self.openrouter_api_key:
            raise RuntimeError("❌ OPENROUTER_API_KEY environment variable is missing or invalid. Please export OPENROUTER_API_KEY=your_key in your shell or .env file before running flowjob.")

        self.llm = ChatOpenAI(
            model=self.model_name,
            api_key=self.openrouter_api_key,
            base_url=self.openrouter_base_url,
            temperature=self.temperature,
            max_tokens=4000
        )
        
    def run(self, context: dict) -> BaseModel:
        # Run preprocessors
        for preprocessor in self.preprocessors:
            context = preprocessor(context)

        prompt = PromptTemplate.from_template(self.prompt_template)
        formatted_prompt = prompt.format(**context)
        
        return invoke_with_schema_tool(self.llm, [formatted_prompt], self.response_schema)


class SchemaExtractionError(Exception):
    pass


def invoke_with_schema_tool(llm: Any, messages: list, schema: Type[BaseModel], retries: int = 3) -> BaseModel:
    """
    Wraps LLM invocation using the schema-as-a-single-tool pattern.
    - Never forces `tool_choice` to avoid upstream 503 errors.
    - Retries on validation or missing tool calls.
    """
    import json
    llm_with_tools = llm.bind_tools([schema])
    
    last_error = None
    for _ in range(retries):
        try:
            response = llm_with_tools.invoke(messages)
            
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
            
        except Exception as e:
            last_error = e
            
    raise last_error

