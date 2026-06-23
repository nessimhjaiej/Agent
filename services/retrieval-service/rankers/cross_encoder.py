"""Cross-encoder reranker (local sentence-transformers model).

Scores each (query, chunk_text) pair with a cross-encoder — more accurate than
the fusion score because the model reads the query and chunk together — then
sorts by that score. The model is loaded lazily on first use.
"""

import os
from dataclasses import replace

from app.errors import RetrievalProviderError
from app.models import CandidateChunk
from rankers.base import BaseRanker


class CrossEncoderRanker(BaseRanker):
    """Rerank candidates with a local cross-encoder model."""

    def __init__(
        self,
        model_name: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self._model_name = model_name or os.getenv(
            "RETRIEVAL_CROSS_ENCODER_MODEL",
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
        )
        self._batch_size = batch_size or int(
            os.getenv("RETRIEVAL_CROSS_ENCODER_BATCH_SIZE", "16")
        )
        self._model = None

    @property
    def name(self) -> str:
        return "cross_encoder"

    def rank(self, query: str, candidates: list[CandidateChunk], top_n: int) -> list[CandidateChunk]:
        if not candidates:
            return []

        model = self._get_model()
        pairs = [[query, candidate.chunk_text] for candidate in candidates]
        try:
            raw_scores = model.predict(
                pairs,
                batch_size=self._batch_size,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise RetrievalProviderError(f"Cross-encoder scoring failed: {exc}") from exc

        scores = [float(score) for score in raw_scores]
        scored = [
            replace(candidate, rerank_score=score)
            for candidate, score in zip(candidates, scores)
        ]
        scored.sort(
            key=lambda x: (
                x.rerank_score if x.rerank_score is not None else float("-inf"),
                x.fusion_score if x.fusion_score is not None else float("-inf"),
            ),
            reverse=True,
        )
        return scored[:top_n]

    def _get_model(self):
        """Lazily import + load the cross-encoder model, caching it after first use."""
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RetrievalProviderError(
                "sentence-transformers is required for cross_encoder reranking. "
                "Install with: pip install sentence-transformers"
            ) from exc
        self._model = CrossEncoder(self._model_name)
        return self._model
