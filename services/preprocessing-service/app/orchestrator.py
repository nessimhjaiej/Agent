from app.models import ChunkRecord, ChunkingContext, NormalizedDocument
from chunking.factory import ChunkerFactory


class PreprocessingOrchestrator:
    def __init__(self, chunk_strategy: str = "overlap") -> None:
        self._chunker = ChunkerFactory.create(chunk_strategy)

    @property
    def chunker_name(self) -> str:
        return self._chunker.name

    def process_document(
        self, document: NormalizedDocument, context: ChunkingContext | None = None
    ) -> list[ChunkRecord]:
        chunking_context = context or ChunkingContext()
        return self._chunker.chunk(document, chunking_context)

