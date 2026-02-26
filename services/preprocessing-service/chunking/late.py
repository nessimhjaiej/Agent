from app.models import ChunkRecord, ChunkingContext, NormalizedDocument
from chunking.base import BaseChunker


class LateChunker(BaseChunker):
    @property
    def name(self) -> str:
        return "late"

    def chunk(
        self, document: NormalizedDocument, context: ChunkingContext
    ) -> list[ChunkRecord]:
        raise NotImplementedError("LateChunker is not implemented yet.")

