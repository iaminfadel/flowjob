from typing import Any, Type, Callable, List
from pydantic import BaseModel
from google import genai
from google.genai import types
from src.agents.runner import AgentRunner
import os

class StructuredLLMAgent(AgentRunner):
    def __init__(self, client: genai.Client, prompt_template: str, response_schema: Type[BaseModel], temperature: float = 0.2, preprocessors: List[Callable] = None):
        super().__init__(client)
        self.prompt_template = prompt_template
        self.response_schema = response_schema
        self.temperature = temperature
        self.preprocessors = preprocessors or []

    def run(self, context: dict) -> BaseModel:
        # Run preprocessors
        for preprocessor in self.preprocessors:
            context = preprocessor(context)

        prompt = self.prompt_template.format(**context)
        
        retries = 3
        while retries > 0:
            try:
                response = self.client.models.generate_content(
                    model="gemini-2.5-pro",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=self.response_schema,
                        temperature=self.temperature,
                    ),
                )
                return response.parsed
            except Exception as e:
                retries -= 1
                if retries == 0:
                    raise e
