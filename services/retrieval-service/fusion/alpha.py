from dataclasses import replace

from app.models import CandidateChunk, QueryContext
from fusion.base import BaseFusion


class AlphaFusion(BaseFusion):
    @property
    def name(self) -> str:
        return "alpha"

    def combine(
        self,
        bm25_candidates: list[CandidateChunk],
        vector_candidates: list[CandidateChunk],
        ctx: QueryContext,
    ) -> list[CandidateChunk]:
        merged = self._merge_candidates(bm25_candidates, vector_candidates)
        if not merged:
            return []

        bm25_raw: dict[str, float] = {}
        vector_raw: dict[str, float] = {}

        for idx, c in enumerate(bm25_candidates, start=1):
            rank = c.rank_bm25 or idx
            bm25_raw[c.chunk_id] = c.bm25_score if c.bm25_score is not None else 1.0 / rank

        for idx, c in enumerate(vector_candidates, start=1):
            rank = c.rank_vector or idx
            vector_raw[c.chunk_id] = c.vector_score if c.vector_score is not None else 1.0 / rank

        bm25_norm = self._normalize_scores(bm25_raw)
        vector_norm = self._normalize_scores(vector_raw)

        alpha = ctx.alpha
        fused: list[CandidateChunk] = []
        for chunk_id, c in merged.items():
            b = bm25_norm.get(chunk_id, 0.0)
            v = vector_norm.get(chunk_id, 0.0)
            score = (1.0 - alpha) * b + alpha * v
            fused.append(replace(c, fusion_score=score))

        fused.sort(
            key=lambda x: (
                x.fusion_score if x.fusion_score is not None else -1.0,
                x.vector_score if x.vector_score is not None else -1.0,
                x.bm25_score if x.bm25_score is not None else -1.0,
                x.chunk_id,
            ),
            reverse=True,
        )
        return fused

    def _normalize_scores(self, scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        values = list(scores.values())
        min_v = min(values)
        max_v = max(values)
        if max_v == min_v:
            return {k: 1.0 for k in scores}
        return {k: (v - min_v) / (max_v - min_v) for k, v in scores.items()}

    def _merge_candidates(
        self,
        bm25_candidates: list[CandidateChunk],
        vector_candidates: list[CandidateChunk],
    ) -> dict[str, CandidateChunk]:
        merged: dict[str, CandidateChunk] = {}
        for c in bm25_candidates:
            merged[c.chunk_id] = c
        for c in vector_candidates:
            existing = merged.get(c.chunk_id)
            if existing is None:
                merged[c.chunk_id] = c
                continue
            merged[c.chunk_id] = replace(
                existing,
                chunk_text=existing.chunk_text or c.chunk_text,
                metadata=existing.metadata or c.metadata,
                vector_score=c.vector_score if c.vector_score is not None else existing.vector_score,
                rank_vector=c.rank_vector if c.rank_vector is not None else existing.rank_vector,
            )
        return merged
