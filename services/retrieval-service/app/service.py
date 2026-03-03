from collections import defaultdict

from app.models import QueryContext
from app.orchestrator import RetrievalOrchestrator
from app.schemas import SearchDocumentResult, SearchRequest, SearchResponse


class RetrievalService:
    def __init__(self) -> None:
        self._orchestrator = RetrievalOrchestrator()

    def search(self, payload: SearchRequest) -> SearchResponse:
        ctx = QueryContext(
            query=payload.query,
            top_k_retrieve=payload.top_k_retrieve,
            top_k_return=payload.top_k_return,
            mode=payload.mode,
            filters=payload.filters,
            fusion_type=payload.fusion.type,
            alpha=payload.fusion.alpha,
            rrf_k=payload.fusion.rrf_k,
            rerank_type=payload.rerank.type,
            rerank_enabled=payload.rerank.enabled,
            rerank_top_n=payload.rerank.top_n,
        )
        candidates = self._orchestrator.search(ctx)
        top = candidates[: payload.top_k_return]

        documents_map: dict[str, list[str]] = defaultdict(list)
        for item in top:
            documents_map[item.document_id].append(item.chunk_id)

        docs = [
            SearchDocumentResult(document_id=doc_id, chunk_ids=chunk_ids, hit_count=len(chunk_ids))
            for doc_id, chunk_ids in documents_map.items()
        ]

        return SearchResponse(
            query=payload.query,
            retrieval_count=len(candidates),
            returned_count=len(top),
            mode=payload.mode,
            fusion_type=payload.fusion.type,
            rerank_type=payload.rerank.type if payload.rerank.enabled else "none",
            chunks=[
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "chunk_text": c.chunk_text,
                    "metadata": c.metadata,
                    "bm25_score": c.bm25_score,
                    "vector_score": c.vector_score,
                    "fusion_score": c.fusion_score,
                    "rerank_score": c.rerank_score,
                }
                for c in top
            ],
            documents=docs,
        )
