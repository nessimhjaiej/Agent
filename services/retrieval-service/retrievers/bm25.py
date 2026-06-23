"""BM25 (keyword) retriever backed by Weaviate's BM25 search."""

from app.config import Settings
from app.models import CandidateChunk, QueryContext
from clients.weaviate_client import WeaviateClient
from retrievers.base import BaseRetriever


class BM25Retriever(BaseRetriever):
    """Keyword retrieval: query Weaviate BM25 and map rows to CandidateChunks."""

    def __init__(self, client: WeaviateClient | None = None) -> None:
        if client is not None:
            self._client = client
            return
        settings = Settings.from_env()
        self._client = WeaviateClient(
            base_url=settings.weaviate_http_url,
            collection=settings.weaviate_collection,
        )

    @property
    def name(self) -> str:
        return "bm25"

    def retrieve(self, ctx: QueryContext) -> list[CandidateChunk]:
        """Run BM25 search and return candidates; `rank_bm25` is the 1-based result order."""
        rows = self._client.bm25_search(
            query=ctx.query,
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

            metadata = {
                key: value
                for key, value in row.items()
                if key not in {"chunk_id", "document_id", "chunk_text", "_additional"}
            }

            additional = row.get("_additional", {})
            score = None
            if isinstance(additional, dict):
                raw = additional.get("score")
                if raw is not None:
                    try:
                        score = float(raw)
                    except (TypeError, ValueError):
                        score = None

            candidates.append(
                CandidateChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    chunk_text=chunk_text,
                    metadata=metadata,
                    bm25_score=score,
                    rank_bm25=idx,
                )
            )
        return candidates
