from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.evaluation.ragas_runner import EvaluationSample, RagasEvaluationRunner  # noqa: E402
from app.schemas import AskResponse, CitationResponse  # noqa: E402


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def ask(self, payload):  # noqa: ANN001
        self.calls.append(payload)
        return AskResponse(
            status="ok",
            query=payload.query,
            answer="A generated answer",
            citations=[
                CitationResponse(
                    chunk_id="doc-1:0",
                    document_id="doc-1",
                    document_name="doc-1.pdf",
                    chunk_text="retrieved context",
                )
            ],
            used_chunk_ids=["doc-1:0"],
            model="gpt-4o",
            retrieval_count=1,
            returned_count=1,
            retrieval_mode="hybrid",
            fusion_type="rrf",
            rerank_type="none",
        )


def test_load_dataset_requires_question_and_reference(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps([{"question": "q1", "reference": "r1"}, {"question": "q2", "reference": "r2"}]),
        encoding="utf-8",
    )

    loaded = RagasEvaluationRunner.load_dataset(dataset_path)

    assert len(loaded) == 2
    assert loaded[0].question == "q1"
    assert loaded[1].reference == "r2"


def test_build_ragas_rows_maps_service_response() -> None:
    runner = RagasEvaluationRunner(service=_FakeService())  # type: ignore[arg-type]
    samples = [EvaluationSample(question="What is AML?", reference="AML means anti-money laundering.")]

    rows = runner.build_ragas_rows(samples)

    assert len(rows) == 1
    assert rows[0]["user_input"] == "What is AML?"
    assert rows[0]["response"] == "A generated answer"
    assert rows[0]["reference"] == "AML means anti-money laundering."
    assert rows[0]["retrieved_contexts"] == ["retrieved context"]


def test_write_report_creates_dated_json_file(tmp_path: Path) -> None:
    fixed_now = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)
    runner = RagasEvaluationRunner(
        service=_FakeService(),  # type: ignore[arg-type]
        reports_dir=tmp_path,
        now_fn=lambda: fixed_now,
    )

    output = runner.write_report(
        dataset_path=Path("evals/sample_eval_dataset.json"),
        sample_count=2,
        summary={"faithfulness": 0.9},
        records=[{"user_input": "q"}],
    )

    assert output.name == "ragas_report_20260307_120000.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["sample_count"] == 2
    assert payload["summary"]["faithfulness"] == 0.9
