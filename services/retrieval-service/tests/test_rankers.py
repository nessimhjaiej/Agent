from pathlib import Path
import sys

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.models import CandidateChunk  # noqa: E402
from rankers.cross_encoder import CrossEncoderRanker  # noqa: E402
from rankers.factory import RankerFactory  # noqa: E402
from rankers.identity import IdentityRanker  # noqa: E402
from rankers.llm_batch import LLMBatchRanker  # noqa: E402


def _chunk(chunk_id: str, text: str, fusion_score: float | None = None) -> CandidateChunk:
    return CandidateChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        chunk_text=text,
        metadata={},
        fusion_score=fusion_score,
    )


class _FakeCrossEncoderModel:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores
        self.calls: list[dict] = []

    def predict(self, pairs: list[list[str]], batch_size: int, show_progress_bar: bool):
        self.calls.append(
            {
                "pairs": pairs,
                "batch_size": batch_size,
                "show_progress_bar": show_progress_bar,
            }
        )
        return self._scores


def test_cross_encoder_ranker_orders_by_rerank_score() -> None:
    ranker = CrossEncoderRanker(model_name="dummy-model", batch_size=8)
    fake_model = _FakeCrossEncoderModel(scores=[0.2, 0.9, 0.4])
    ranker._model = fake_model

    candidates = [
        _chunk("a", "text a", fusion_score=0.8),
        _chunk("b", "text b", fusion_score=0.1),
        _chunk("c", "text c", fusion_score=0.5),
    ]
    ranked = ranker.rank("query", candidates, top_n=2)

    assert len(fake_model.calls) == 1
    assert fake_model.calls[0]["batch_size"] == 8
    assert [item.chunk_id for item in ranked] == ["b", "c"]
    assert ranked[0].rerank_score == 0.9
    assert ranked[1].rerank_score == 0.4


def test_cross_encoder_ranker_returns_empty_for_empty_input() -> None:
    ranker = CrossEncoderRanker(model_name="dummy-model")
    ranker._model = _FakeCrossEncoderModel(scores=[])

    ranked = ranker.rank("query", [], top_n=5)

    assert ranked == []


def test_ranker_factory_returns_identity_when_disabled() -> None:
    ranker = RankerFactory.create("cross_encoder", enabled=False)

    assert isinstance(ranker, IdentityRanker)


def test_ranker_factory_raises_for_unknown_enabled_ranker() -> None:
    with pytest.raises(ValueError):
        RankerFactory.create("unknown", enabled=True)


def test_llm_batch_ranker_orders_by_llm_scores() -> None:
    ranker = LLMBatchRanker(api_key="test-key", batch_size=10)
    ranker._score_all_batches = lambda query, candidates: [  # type: ignore[method-assign]
        ("b", 0.95),
        ("a", 0.40),
    ]
    candidates = [
        _chunk("a", "text a", fusion_score=0.8),
        _chunk("b", "text b", fusion_score=0.2),
    ]

    ranked = ranker.rank("query", candidates, top_n=2)

    assert [item.chunk_id for item in ranked] == ["b", "a"]
    assert ranked[0].rerank_score == 0.95
    assert ranked[1].rerank_score == 0.40


def test_llm_batch_ranker_falls_back_to_original_order_on_failure() -> None:
    ranker = LLMBatchRanker(api_key="test-key", batch_size=10)

    def _raise(_query, _candidates):  # noqa: ANN001
        raise RuntimeError("model failed")

    ranker._score_all_batches = _raise  # type: ignore[method-assign]
    candidates = [
        _chunk("a", "text a", fusion_score=0.8),
        _chunk("b", "text b", fusion_score=0.2),
    ]

    ranked = ranker.rank("query", candidates, top_n=2)

    assert [item.chunk_id for item in ranked] == ["a", "b"]
    assert all(item.rerank_score is None for item in ranked)


def test_llm_batch_parse_scores_json_accepts_fenced_json() -> None:
    ranker = LLMBatchRanker(api_key="test-key")
    raw = """```json
    {"scores":[{"chunk_id":"a","score":0.7}]}
    ```"""

    parsed = ranker._parse_scores_json(raw)  # type: ignore[attr-defined]

    assert parsed == [{"chunk_id": "a", "score": 0.7}]
