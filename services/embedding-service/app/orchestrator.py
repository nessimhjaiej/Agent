from app.config import Settings
from app.errors import VectorStoreError
from app.models import Chunk, IndexChunkResult
from embeddings.base import BaseEmbedder
from embeddings.openai_embedder import OpenAIEmbedder
from indexers.base import BaseVectorIndexer
from indexers.weaviate_indexer import WeaviateIndexer


class EmbeddingOrchestrator:
    def __init__(
        self,
        settings: Settings,
        embedder: BaseEmbedder | None = None,
        indexer: BaseVectorIndexer | None = None,
    ) -> None:
        self._settings = settings
        self._embedder = embedder or OpenAIEmbedder(settings)
        self._indexer = indexer or WeaviateIndexer(settings)

    def index_chunks(self, chunks: list[Chunk]) -> list[IndexChunkResult]:
        seen_counts: dict[str, int] = {}
        unique_chunks: list[Chunk] = []

        for chunk in chunks:
            count = seen_counts.get(chunk.chunk_id, 0) + 1
            seen_counts[chunk.chunk_id] = count
            if count == 1:
                unique_chunks.append(chunk)

        if not unique_chunks:
            return []

        vectors = self._embedder.embed_texts([chunk.chunk_text for chunk in unique_chunks])
        if len(vectors) != len(unique_chunks):
            raise VectorStoreError("Embedding output count does not match chunk count")

        self._validate_vector_dimensions(vectors)
        index_results = self._indexer.upsert_chunks(unique_chunks, vectors)
        by_chunk_id = {result.chunk_id: result for result in index_results}

        final_results: list[IndexChunkResult] = []
        emitted_first: set[str] = set()
        for chunk in chunks:
            if chunk.chunk_id in emitted_first:
                final_results.append(
                    IndexChunkResult(
                        chunk_id=chunk.chunk_id,
                        indexed=False,
                        reason="duplicate_chunk_id_in_request",
                    )
                )
                continue
            emitted_first.add(chunk.chunk_id)
            final_results.append(
                by_chunk_id.get(
                    chunk.chunk_id,
                    IndexChunkResult(
                        chunk_id=chunk.chunk_id,
                        indexed=False,
                        reason="index_result_missing",
                    ),
                )
            )
        return final_results

    def _validate_vector_dimensions(self, vectors: list[list[float]]) -> None:
        if not vectors:
            return

        expected = self._settings.embedding_dimensions or len(vectors[0])
        for vector in vectors:
            if len(vector) != expected:
                raise VectorStoreError(
                    f"Vector dimension mismatch. Expected {expected}, got {len(vector)}"
                )
