from collections import defaultdict
from pathlib import Path

from app.config import Settings
from app.models import QueryContext
from app.orchestrator import RetrievalOrchestrator
from app.schemas import FusionOptions, RerankOptions, SearchDocumentResult, SearchRequest, SearchResponse


class RetrievalService:
    def __init__(
        self,
        settings: Settings | None = None,
        orchestrator: RetrievalOrchestrator | None = None,
    ) -> None:
        self._settings = settings or Settings.from_env()
        self._orchestrator = orchestrator or RetrievalOrchestrator()

    def search(self, payload: SearchRequest) -> SearchResponse:
        fusion = payload.fusion or FusionOptions()
        fusion_type = fusion.type or self._settings.default_fusion_type
        alpha = fusion.alpha if fusion.alpha is not None else self._settings.default_alpha
        rrf_k = fusion.rrf_k if fusion.rrf_k is not None else self._settings.default_rrf_k

        rerank = payload.rerank or RerankOptions()
        rerank_type = rerank.type or self._settings.default_ranker_type
        rerank_enabled = (
            rerank.enabled if rerank.enabled is not None else rerank_type != "none"
        )
        rerank_top_n = (
            rerank.top_n if rerank.top_n is not None else self._settings.default_rerank_top_n
        )

        top_k_retrieve = (
            payload.top_k_retrieve
            if payload.top_k_retrieve is not None
            else self._settings.default_top_k_retrieve
        )
        top_k_return = (
            payload.top_k_return
            if payload.top_k_return is not None
            else self._settings.default_top_k_return
        )

        ctx = QueryContext(
            query=payload.query,
            top_k_retrieve=top_k_retrieve,
            top_k_return=top_k_return,
            mode=payload.mode,
            filters=payload.filters,
            fusion_type=fusion_type,
            alpha=alpha,
            rrf_k=rrf_k,
            rerank_type=rerank_type,
            rerank_enabled=rerank_enabled,
            rerank_top_n=rerank_top_n,
        )
        candidates = self._orchestrator.search(ctx)
        top = candidates[:top_k_return]

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
            fusion_type=fusion_type,
            rerank_type=rerank_type if rerank_enabled else "none",
            chunks=[
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "document_name": self._resolve_document_name(c.document_id, c.metadata),
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

    def _resolve_document_name(self, document_id: str, metadata: dict) -> str:
        source_filename = metadata.get("source_filename")
        if isinstance(source_filename, str) and source_filename.strip():
            return source_filename.strip()

        source_uri = metadata.get("source_uri")
        if isinstance(source_uri, str) and source_uri.strip():
            raw = source_uri.strip().rstrip("/\\")
            if raw:
                return Path(raw).name or document_id

        return document_id
