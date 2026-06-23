"""Alpha (weighted) fusion of BM25 and vector results.

Each list's scores are min-max normalized to [0, 1] (so the two scales are
comparable), then blended: ``score = (1 - alpha) * bm25 + alpha * vector``.
``alpha`` (default 0.7) controls the lean: 0 = keyword only, 1 = semantic only.
"""

from dataclasses import replace

from app.models import CandidateChunk, QueryContext
from fusion.base import BaseFusion


class AlphaFusion(BaseFusion):
    """Weighted fusion: blend min-max-normalized BM25 and vector scores by ``alpha``."""

    @property
    def name(self) -> str:
        return "alpha"

    def combine(
        self,
        bm25_candidates: list[CandidateChunk],
        vector_candidates: list[CandidateChunk],
        ctx: QueryContext,
    ) -> list[CandidateChunk]:
        """Fuse the two lists into one, ordered by descending blended score."""
        merged = self._merge_candidates(bm25_candidates, vector_candidates)
        if not merged:
            return []

        # Collect each list's raw scores (fall back to 1/rank when a score is
        # missing), so both branches always contribute a comparable signal.

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
        """Min-max scale scores to [0, 1] (all-equal scores collapse to 1.0)."""
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
