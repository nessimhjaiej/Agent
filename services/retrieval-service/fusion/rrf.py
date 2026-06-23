"""Reciprocal Rank Fusion (RRF) for combining BM25 and vector result lists.

RRF ignores raw scores and uses only each item's *rank* in each list, which makes
it robust when BM25 and vector scores are on different scales. A chunk's fused
score is the sum over the lists it appears in of ``1 / (k + rank)``, where ``k``
(``rrf_k``, default 60) dampens the influence of top ranks.
"""

from dataclasses import replace

from app.models import CandidateChunk, QueryContext
from fusion.base import BaseFusion


class RRFFusion(BaseFusion):
    """Rank-based fusion: score = Σ 1/(k + rank) across the BM25 and vector lists."""

    @property
    def name(self) -> str:
        return "rrf"

    def combine(
        self,
        bm25_candidates: list[CandidateChunk],
        vector_candidates: list[CandidateChunk],
        ctx: QueryContext,
    ) -> list[CandidateChunk]:
        """Fuse the two ranked lists into one, ordered by descending RRF score."""
        merged = self._merge_candidates(bm25_candidates, vector_candidates)
        if not merged:
            return []

        # Map each chunk to its 1-based rank in each list (fall back to the loop
        # index when a precomputed rank is absent).

        bm25_rank: dict[str, int] = {}
        vector_rank: dict[str, int] = {}
        for idx, c in enumerate(bm25_candidates, start=1):
            bm25_rank[c.chunk_id] = c.rank_bm25 or idx
        for idx, c in enumerate(vector_candidates, start=1):
            vector_rank[c.chunk_id] = c.rank_vector or idx

        k = ctx.rrf_k
        fused: list[CandidateChunk] = []
        for chunk_id, c in merged.items():
            score = 0.0
            br = bm25_rank.get(chunk_id)
            vr = vector_rank.get(chunk_id)
            if br is not None:
                score += 1.0 / (k + br)
            if vr is not None:
                score += 1.0 / (k + vr)
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

    def _merge_candidates(
        self,
        bm25_candidates: list[CandidateChunk],
        vector_candidates: list[CandidateChunk],
    ) -> dict[str, CandidateChunk]:
        """Union the two lists by chunk_id, preferring populated fields from each."""
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
