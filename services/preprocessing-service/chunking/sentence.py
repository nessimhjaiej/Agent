from app.models import ChunkRecord, ChunkingContext, NormalizedDocument
from chunking.base import BaseChunker


class SentenceChunker(BaseChunker):
    @property
    def name(self) -> str:
        return "sentence"

    def chunk(
        self, document: NormalizedDocument, context: ChunkingContext
    ) -> list[ChunkRecord]:
        raise NotImplementedError("SentenceChunker is not implemented yet.")

