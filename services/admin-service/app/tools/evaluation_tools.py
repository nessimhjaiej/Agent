from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.models import ToolExecutionResult


class EvaluationReportStore:
    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path(__file__).resolve().parents[4]
        self._generation_service_dir = self._project_root / "services" / "generation-service"
        self._reports_dir = self._generation_service_dir / "evaluation_reports"

    def run(self, dataset_path: str) -> dict:
        command = [
            sys.executable,
            "-m",
            "app.evaluation.ragas_runner",
            "--dataset",
            dataset_path,
        ]
        completed = subprocess.run(
            command,
            cwd=self._generation_service_dir,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip() or "unknown error"
            raise RuntimeError(f"Evaluation runner failed: {detail}")
        report_path = self._find_latest_report()
        return self.load_report(str(report_path))

    def load_report(self, report_path: str | None = None) -> dict:
        path = self._resolve_report_path(report_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Evaluation report is not a JSON object")
        payload["report_path"] = str(path)
        return payload

    def _find_latest_report(self) -> Path:
        candidates = sorted(
            self._reports_dir.glob("ragas_report_*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise RuntimeError("No evaluation reports were found after the run completed")
        return candidates[0]

    def _resolve_report_path(self, report_path: str | None) -> Path:
        if report_path:
            candidate = Path(report_path)
            if not candidate.is_absolute():
                candidate = (self._project_root / report_path).resolve()
        else:
            candidate = self._find_latest_report()

        if not candidate.exists():
            raise RuntimeError(f"Evaluation report not found: {candidate}")
        return candidate


class RunRagEvaluationTool:
    name = "run_rag_evaluation"

    def __init__(self, report_store: EvaluationReportStore | None = None) -> None:
        self._report_store = report_store or EvaluationReportStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        dataset_path = str(arguments.get("dataset_path", "evals/sample_eval_dataset.json")).strip()
        if not dataset_path:
            dataset_path = "evals/sample_eval_dataset.json"

        report = self._report_store.run(dataset_path)
        summary = report.get("summary", {})
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"RAG evaluation completed for {report.get('sample_count', 0)} samples. "
                f"Report saved at '{report.get('report_path', '')}'."
            ),
            result={
                "dataset_path": report.get("dataset_path", dataset_path),
                "report_path": report.get("report_path", ""),
                "generated_at_utc": report.get("generated_at_utc", ""),
                "sample_count": report.get("sample_count", 0),
                "summary": summary if isinstance(summary, dict) else {},
            },
        )


class GetEvaluationReportTool:
    name = "get_evaluation_report"

    def __init__(self, report_store: EvaluationReportStore | None = None) -> None:
        self._report_store = report_store or EvaluationReportStore()

    def execute(self, arguments: dict) -> ToolExecutionResult:
        report_path_raw = str(arguments.get("report_path", "")).strip()
        report = self._report_store.load_report(report_path_raw or None)
        summary = report.get("summary", {})
        return ToolExecutionResult(
            status="ok",
            answer=(
                f"Loaded evaluation report '{Path(str(report.get('report_path', ''))).name}' "
                f"with {report.get('sample_count', 0)} samples."
            ),
            result={
                "report_path": report.get("report_path", ""),
                "dataset_path": report.get("dataset_path", ""),
                "generated_at_utc": report.get("generated_at_utc", ""),
                "sample_count": report.get("sample_count", 0),
                "summary": summary if isinstance(summary, dict) else {},
                "records": report.get("records", []),
            },
        )
