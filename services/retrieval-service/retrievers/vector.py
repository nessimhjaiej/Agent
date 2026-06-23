"""Vector (semantic) retriever: embed the query, then nearVector search Weaviate."""

from app.config import Settings
from app.errors import RetrievalValidationError
from app.models import CandidateChunk, QueryContext
from clients.openai_client import OpenAIClient
from clients.weaviate_client import WeaviateClient
from retrievers.base import BaseRetriever


class VectorRetriever(BaseRetriever):
    """Semantic retrieval: OpenAI-embed the query and nearVector-search Weaviate."""

    def __init__(
        self,
        embedder: OpenAIClient | None = None,
        weaviate_client: WeaviateClient | None = None,
    ) -> None:
        settings = Settings.from_env()
        self._embedder = embedder or OpenAIClient(
            api_key=settings.openai_key,
            model=settings.embedding_model,
        )
        self._embedding_model = settings.embedding_model
        self._enforce_embedding_model_match = settings.enforce_embedding_model_match
        self._weaviate = weaviate_client or WeaviateClient(
            base_url=settings.weaviate_http_url,
            collection=settings.weaviate_collection,
        )

    @property
    def name(self) -> str:
        return "vector"

    def retrieve(self, ctx: QueryContext) -> list[CandidateChunk]:
        """Embed the query and search Weaviate; `vector_score = 1 - distance`.

        Guards against a query/index embedding-model mismatch (which would make
        distances meaningless) when `enforce_embedding_model_match` is on.
        """
        query_vector = self._embedder.embed_query(ctx.query)
        rows = self._weaviate.vector_search(
            query_vector=query_vector,
            top_k=ctx.top_k_retrieve,
            filters=ctx.filters,
        )

        candidates: list[CandidateChunk] = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            chunk_id = str(row.get("chunk_id", ""))
            document_id = str(row.get("document_id", ""))
            chunk_text = str(row.get("chunk_text", ""))
            if not chunk_id or not document_id:
                continue

            row_embedding_model = row.get("embedding_model")
            if self._enforce_embedding_model_match:
                if isinstance(row_embedding_model, str) and row_embedding_model.strip() and row_embedding_model.strip() != self._embedding_model:
                    raise RetrievalValidationError(
                        "Embedding model mismatch between query and indexed chunk. "
                        f"query_model={self._embedding_model}, chunk_model={row_embedding_model.strip()}"
                    )

            metadata = {
                key: value
                for key, value in row.items()
                if key not in {"chunk_id", "document_id", "chunk_text", "_additional"}
            }

            additional = row.get("_additional", {})
            vector_score = None
            if isinstance(additional, dict):
                raw_distance = additional.get("distance")
                if raw_distance is not None:
                    try:
                        distance = float(raw_distance)
                        vector_score = 1.0 - distance
                    except (TypeError, ValueError):
                        vector_score = None

            candidates.append(
                CandidateChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    chunk_text=chunk_text,
                    metadata=metadata,
                    vector_score=vector_score,
                    rank_vector=idx,
                )
            )
        return candidates
