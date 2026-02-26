from abc import ABC, abstractmethod

from app.models import ChunkRecord, NormalizedDocument, RawDocument


class BaseMetadataBuilder(ABC):
    @abstractmethod
    def enrich(
        self,
        chunks: list[ChunkRecord],
        normalized_document: NormalizedDocument,
        raw_document: RawDocument | None = None,
    ) -> list[ChunkRecord]:
        raise NotImplementedError

