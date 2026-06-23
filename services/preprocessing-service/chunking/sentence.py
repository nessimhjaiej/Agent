"""Sentence chunker — registered strategy, not yet implemented (placeholder)."""

from app.models import ChunkRecord, ChunkingContext, NormalizedDocument
from chunking.base import BaseChunker


class SentenceChunker(BaseChunker):
    """Placeholder for sentence-boundary chunking; raises until implemented."""

    @property
    def name(self) -> str:
        return "sentence"

    def chunk(
        self, document: NormalizedDocument, context: ChunkingContext
    ) -> list[ChunkRecord]:
        raise NotImplementedError("SentenceChunker is not implemented yet.")

