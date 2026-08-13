from abc import ABC, abstractmethod
from typing import Any

class AgentRunner(ABC):
    """
    Abstract base class for all AGY SDK agents.
    Provides a standardized interface for the orchestrator to invoke agents.
    """
    
    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        """Execute the agent's core logic."""
        pass
