import pytest
from src.agents.runner import AgentRunner

class DummyAgent(AgentRunner):
    def run(self):
        pass

def test_agent_runner_accepts_client():
    client = "mock_client"
    agent = DummyAgent(client=client)
    assert agent.client == client

def test_agent_runner_works_without_client():
    agent = DummyAgent()
    assert agent.client is None
