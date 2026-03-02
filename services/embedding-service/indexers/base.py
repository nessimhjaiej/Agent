from abc import ABC, abstractmethod

from app.models import Chunk, IndexChunkResult


class BaseVectorIndexer(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def upsert_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> list[IndexChunkResult]:
        raise NotImplementedError
