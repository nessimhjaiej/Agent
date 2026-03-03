from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.models import CandidateChunk, QueryContext  # noqa: E402
from fusion.alpha import AlphaFusion  # noqa: E402
from fusion.factory import FusionFactory  # noqa: E402
from fusion.rrf import RRFFusion  # noqa: E402
import pytest  # noqa: E402


def _chunk(
    chunk_id: str,
    *,
    bm25_score: float | None = None,
    vector_score: float | None = None,
    rank_bm25: int | None = None,
    rank_vector: int | None = None,
) -> CandidateChunk:
    return CandidateChunk(
        chunk_id=chunk_id,
        document_id="doc",
        chunk_text=f"text-{chunk_id}",
        metadata={},
        bm25_score=bm25_score,
        vector_score=vector_score,
        rank_bm25=rank_bm25,
        rank_vector=rank_vector,
    )


def test_alpha_fusion_combines_normalized_scores_with_vector_bias() -> None:
    bm25 = [
        _chunk("a", bm25_score=2.0, rank_bm25=1),
        _chunk("b", bm25_score=1.0, rank_bm25=2),
    ]
    vector = [
        _chunk("a", vector_score=0.20, rank_vector=2),
        _chunk("b", vector_score=0.90, rank_vector=1),
        _chunk("c", vector_score=0.50, rank_vector=3),
    ]
    ctx = QueryContext(query="q", top_k_retrieve=5, top_k_return=3, alpha=0.7)

    fused = AlphaFusion().combine(bm25, vector, ctx)

    assert [c.chunk_id for c in fused][:2] == ["b", "a"]
    by_id = {c.chunk_id: c for c in fused}
    assert by_id["b"].fusion_score is not None
    assert by_id["a"].fusion_score is not None
    assert by_id["b"].fusion_score > by_id["a"].fusion_score
    assert by_id["c"].fusion_score is not None


def test_rrf_fusion_prefers_items_present_in_both_rankings() -> None:
    bm25 = [
        _chunk("a", bm25_score=1.5, rank_bm25=1),
        _chunk("b", bm25_score=1.2, rank_bm25=2),
    ]
    vector = [
        _chunk("b", vector_score=0.9, rank_vector=1),
        _chunk("c", vector_score=0.8, rank_vector=2),
        _chunk("a", vector_score=0.6, rank_vector=3),
    ]
    ctx = QueryContext(query="q", top_k_retrieve=5, top_k_return=3, rrf_k=60)

    fused = RRFFusion().combine(bm25, vector, ctx)
    by_id = {c.chunk_id: c for c in fused}

    assert by_id["b"].fusion_score is not None
    assert by_id["a"].fusion_score is not None
    assert by_id["c"].fusion_score is not None
    assert by_id["b"].fusion_score > by_id["c"].fusion_score
    assert by_id["a"].fusion_score > by_id["c"].fusion_score


def test_fusion_factory_returns_expected_types() -> None:
    assert isinstance(FusionFactory.create("alpha"), AlphaFusion)
    assert isinstance(FusionFactory.create("rrf"), RRFFusion)


def test_fusion_factory_raises_for_unknown_type() -> None:
    with pytest.raises(ValueError):
        FusionFactory.create("unknown")
