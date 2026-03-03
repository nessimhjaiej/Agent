from abc import ABC, abstractmethod

from app.models import CandidateChunk


class BaseRanker(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def rank(self, query: str, candidates: list[CandidateChunk], top_n: int) -> list[CandidateChunk]:
        raise NotImplementedError
