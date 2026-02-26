from abc import ABC, abstractmethod

from app.models import ChunkRecord, ChunkingContext, NormalizedDocument


class BaseChunker(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def chunk(
        self, document: NormalizedDocument, context: ChunkingContext
    ) -> list[ChunkRecord]:
        raise NotImplementedError

