from app.models import ChunkRecord, ChunkingContext, NormalizedDocument
from chunking.base import BaseChunker


class SemanticChunker(BaseChunker):
    @property
    def name(self) -> str:
        return "semantic"

    def chunk(
        self, document: NormalizedDocument, context: ChunkingContext
    ) -> list[ChunkRecord]:
        raise NotImplementedError("SemanticChunker is not implemented yet.")

