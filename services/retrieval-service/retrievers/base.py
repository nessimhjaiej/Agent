from abc import ABC, abstractmethod

from app.models import CandidateChunk, QueryContext


class BaseRetriever(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, ctx: QueryContext) -> list[CandidateChunk]:
        raise NotImplementedError
