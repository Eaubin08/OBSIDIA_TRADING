from __future__ import annotations

from abc import ABC, abstractmethod
from .contracts import AgentVote


class BaseAgent(ABC):
    agent_id: str = "BaseAgent"

    @abstractmethod
    def evaluate(self, state) -> AgentVote:
        raise NotImplementedError

    @staticmethod
    def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))
