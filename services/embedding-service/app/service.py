from app.config import Settings
from app.models import Chunk, ChunkMetadata, IndexChunkResult
from app.orchestrator import EmbeddingOrchestrator
from app.schemas import ChunkInput


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._orchestrator = EmbeddingOrchestrator(settings=settings)

    def index_chunks(self, chunks: list[ChunkInput]) -> list[IndexChunkResult]:
        domain_chunks = [self._to_domain_chunk(chunk) for chunk in chunks]
        return self._orchestrator.index_chunks(domain_chunks)

    def _to_domain_chunk(self, chunk: ChunkInput) -> Chunk:
        return Chunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            chunk_text=chunk.chunk_text,
            metadata=ChunkMetadata(
                source_type=chunk.metadata.source_type,
                source_uri=chunk.metadata.source_uri,
                language=chunk.metadata.language,
                chunk_index=chunk.metadata.chunk_index,
                start_char=chunk.metadata.start_char,
                end_char=chunk.metadata.end_char,
                char_count=chunk.metadata.char_count,
                token_count_estimate=chunk.metadata.token_count_estimate,
                chunking_strategy=chunk.metadata.chunking_strategy,
                source_filename=chunk.metadata.source_filename,
                document_checksum=chunk.metadata.document_checksum,
                normalization_version=chunk.metadata.normalization_version,
                pipeline_version=chunk.metadata.pipeline_version,
                created_at=chunk.metadata.created_at,
            ),
        )
