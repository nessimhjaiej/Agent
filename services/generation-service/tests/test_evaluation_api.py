from __future__ import annotations

import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))
for module_name in [name for name in list(sys.modules) if name == "app" or name.startswith("app.")]:
    sys.modules.pop(module_name, None)

from app.main import create_app
import app.routers.generation as generation_router_module


def test_list_evaluations_returns_reports(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "ragas_report_20260410_120000.json").write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-04-10T12:00:00+00:00",
                "dataset_path": "evals/sample_eval_dataset.json",
                "sample_count": 3,
                "summary": {"faithfulness": 0.91},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(generation_router_module, "_reports_dir", lambda: reports_dir)

    client = TestClient(create_app())
    response = client.get("/generation/evaluations")

    assert response.status_code == 200
    body = response.json()
    assert body["reports"][0]["report_id"] == "ragas_report_20260410_120000"
    assert body["reports"][0]["summary"]["faithfulness"] == 0.91


def test_get_evaluation_returns_detail(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "ragas_report_20260410_120000.json").write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-04-10T12:00:00+00:00",
                "dataset_path": "evals/sample_eval_dataset.json",
                "sample_count": 1,
                "summary": {"faithfulness": 0.91},
                "records": [
                    {
                        "user_input": "What is AML?",
                        "response": "AML means anti-money laundering.",
                        "reference": "AML means anti-money laundering.",
                        "retrieved_contexts": ["AML stands for anti-money laundering."],
                        "faithfulness": 0.91,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(generation_router_module, "_reports_dir", lambda: reports_dir)

    client = TestClient(create_app())
    response = client.get("/generation/evaluations/ragas_report_20260410_120000")

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["report_id"] == "ragas_report_20260410_120000"
    assert body["report"]["records"][0]["user_input"] == "What is AML?"
    assert body["report"]["records"][0]["metrics"]["faithfulness"] == 0.91


def test_run_evaluation_uses_runner_and_returns_summary(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    reports_dir = tmp_path / "reports"
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text("[]", encoding="utf-8")

    class _FakeRunner:
        def __init__(self, reports_dir: Path | None = None) -> None:
            self.reports_dir = reports_dir

        def run(self, incoming_dataset_path: Path) -> Path:
            assert incoming_dataset_path == dataset_path
            output = reports_dir / "ragas_report_20260410_120500.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-04-10T12:05:00+00:00",
                        "dataset_path": str(incoming_dataset_path),
                        "sample_count": 2,
                        "summary": {"context_recall": 0.88},
                    }
                ),
                encoding="utf-8",
            )
            return output

    class _FakeSettings:
        app_name = "generation-service"
        app_version = "0.1.0"
        evaluation_reports_dir = str(reports_dir)
        project_root = tmp_path

    monkeypatch.setattr(generation_router_module, "RagasEvaluationRunner", _FakeRunner)
    monkeypatch.setattr(generation_router_module.Settings, "from_env", lambda: _FakeSettings())

    client = TestClient(create_app())
    response = client.post("/generation/evaluations/run", json={"dataset_path": str(dataset_path)})

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["report_id"] == "ragas_report_20260410_120500"
    assert body["report"]["summary"]["context_recall"] == 0.88


def test_run_evaluation_resolves_dataset_from_service_root(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    reports_dir = tmp_path / "reports"
    service_root = tmp_path / "services" / "generation-service"
    dataset_path = service_root / "evals" / "sample_eval_dataset.json"
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_text("[]", encoding="utf-8")

    class _FakeRunner:
        def __init__(self, reports_dir: Path | None = None) -> None:
            self.reports_dir = reports_dir

        def run(self, incoming_dataset_path: Path) -> Path:
            assert incoming_dataset_path == dataset_path
            output = reports_dir / "ragas_report_20260410_120500.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-04-10T12:05:00+00:00",
                        "dataset_path": str(incoming_dataset_path),
                        "sample_count": 2,
                        "summary": {"context_recall": 0.88},
                    }
                ),
                encoding="utf-8",
            )
            return output

    class _FakeSettings:
        app_name = "generation-service"
        app_version = "0.1.0"
        evaluation_reports_dir = str(reports_dir)
        project_root = tmp_path

    monkeypatch.setattr(generation_router_module, "RagasEvaluationRunner", _FakeRunner)
    monkeypatch.setattr(generation_router_module.Settings, "from_env", lambda: _FakeSettings())
    monkeypatch.setattr(generation_router_module, "__file__", str(service_root / "app" / "routers" / "generation.py"))

    client = TestClient(create_app())
    response = client.post("/generation/evaluations/run", json={"dataset_path": "evals/sample_eval_dataset.json"})

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["report_id"] == "ragas_report_20260410_120500"
    assert body["report"]["summary"]["context_recall"] == 0.88


def test_compare_evaluations_returns_metric_deltas(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "baseline.json").write_text(
        json.dumps({"summary": {"faithfulness": 0.8, "context_recall": 0.7}}),
        encoding="utf-8",
    )
    (reports_dir / "candidate.json").write_text(
        json.dumps({"summary": {"faithfulness": 0.85, "context_recall": 0.65}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(generation_router_module, "_reports_dir", lambda: reports_dir)

    client = TestClient(create_app())
    response = client.post(
        "/generation/evaluations/compare",
        json={"baseline_report_id": "baseline", "candidate_report_id": "candidate"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["faithfulness"]["delta"] == 0.05
    assert body["metrics"]["context_recall"]["delta"] == -0.05
