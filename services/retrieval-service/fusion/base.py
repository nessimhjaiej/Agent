from abc import ABC, abstractmethod

from app.models import CandidateChunk, QueryContext


class BaseFusion(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def combine(
        self,
        bm25_candidates: list[CandidateChunk],
        vector_candidates: list[CandidateChunk],
        ctx: QueryContext,
    ) -> list[CandidateChunk]:
        raise NotImplementedError
