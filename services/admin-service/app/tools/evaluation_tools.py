from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx

from app.models import ToolExecutionResult
from app.tools.base import ToolMetadata


class EvaluationReportStore:
    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path(__file__).resolve().parents[4]
        self._generation_service_dir = self._project_root / "services" / "generation-service"
        self._reports_dir = self._project_root / "docs" / "evaluation_reports"

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
            candidates = sorted(
                self._reports_dir.glob("*.json"),
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


class EvaluationReportSummarizer:
    def __init__(self, api_key: str, model: str, timeout_seconds: float) -> None:
        self._model = model
        self._client = httpx.Client(
            base_url="https://api.openai.com/v1",
            timeout=timeout_seconds,
            trust_env=False,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def summarize(self, report: dict) -> str:
        prompt = self._build_prompt(report)
        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "temperature": 0.1,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You summarize RAG evaluation reports for admins. "
                            "Be concise, structured, and practical. "
                            "Briefly explain each metric in plain language."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
        )
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI summary request failed {response.status_code}: {response.text}")
        payload = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenAI summary response missing choices")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenAI summary content missing")
        return content.strip()

    def _build_prompt(self, report: dict) -> str:
        summary = report.get("summary", {})
        records = report.get("records", [])
        compact_records = []
        if isinstance(records, list):
            for item in records[:3]:
                if not isinstance(item, dict):
                    continue
                compact_records.append(
                    {
                        "question": item.get("user_input", ""),
                        "response": item.get("response", ""),
                        "reference": item.get("reference", ""),
                        "metrics": {
                            key: value
                            for key, value in item.items()
                            if key not in {"user_input", "response", "reference", "retrieved_contexts"}
                        },
                    }
                )
        payload = {
            "report_path": report.get("report_path", ""),
            "generated_at_utc": report.get("generated_at_utc", ""),
            "dataset_path": report.get("dataset_path", ""),
            "sample_count": report.get("sample_count", 0),
            "summary": summary if isinstance(summary, dict) else {},
            "records_preview": compact_records,
        }
        return (
            "Summarize this evaluation report for an admin.\n"
            "Use this format:\n"
            "Overall\n"
            "- one or two sentences\n"
            "Metrics\n"
            "- one bullet per metric: metric name, score, brief explanation, what it suggests\n"
            "Concerns\n"
            "- short bullets only if needed\n\n"
            f"{json.dumps(payload, ensure_ascii=True, indent=2)}"
        )


def _format_metric_label(metric_name: str) -> str:
    return metric_name.replace("(mode=f1)", " F1").replace("_", " ").strip().title()


def _metric_explanation(metric_name: str) -> str:
    lowered = metric_name.lower()
    if "context_recall" in lowered:
        return "how much of the reference-relevant information was present in the retrieved context"
    if "faithfulness" in lowered:
        return "how well the answer stayed grounded in the retrieved context"
    if "factual_correctness" in lowered:
        return "how closely the answer matched the reference answer"
    return "an evaluation signal for answer quality"


def _fallback_summary(report: dict) -> str:
    summary = report.get("summary", {})
    sample_count = int(report.get("sample_count", 0) or 0)
    lines = [f"Overall\nReviewed {sample_count} evaluation samples from the latest report."]
    if isinstance(summary, dict) and summary:
        lines.append("\nMetrics")
        for key, value in summary.items():
            try:
                score = float(value)
                score_text = f"{score:.3f}"
            except (TypeError, ValueError):
                score_text = str(value)
            lines.append(
                f"- {_format_metric_label(key)}: {score_text}. {_metric_explanation(key)}."
            )
    records = report.get("records", [])
    concerns: list[str] = []
    if isinstance(summary, dict):
        for key, value in summary.items():
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            if score < 0.3:
                concerns.append(f"{_format_metric_label(key)} is low, which suggests a significant quality gap.")
    if isinstance(records, list) and records:
        first = records[0]
        if isinstance(first, dict) and first.get("user_input"):
            concerns.append(f"Example question in this report: {first.get('user_input')}")
    if concerns:
        lines.append("\nConcerns")
        lines.extend(f"- {item}" for item in concerns[:3])
    return "\n".join(lines)


class RunRagEvaluationTool:
    name = "run_rag_evaluation"
    metadata = ToolMetadata(
        name=name,
        description="Run an offline RAG evaluation job and summarize the resulting report.",
        arguments_schema={
            "dataset_path": {
                "type": "string",
                "required": False,
                "description": "Path to the evaluation dataset JSON file.",
            }
        },
        output_description="Returns the dataset path, generated report path, generation timestamp, sample count, and metric summary.",
        requires_confirmation=False,
        goal_tags=["quality", "validation", "risk_reduction", "benchmarking"],
        affects=["evaluation"],
        impact_summary="Runs a validation workflow to measure the impact of a planned or recent configuration change.",
        expected_tradeoffs=[
            "Evaluation consumes time and compute cost but reduces configuration guesswork.",
            "Evaluation does not change production behavior directly.",
        ],
        best_for=["post-change validation", "baseline comparison", "quality measurement"],
        risk_level="medium",
        typical_followups=["get_evaluation_report"],
    )

    def __init__(
        self,
        report_store: EvaluationReportStore | None = None,
        summarizer: EvaluationReportSummarizer | None = None,
    ) -> None:
        self._report_store = report_store or EvaluationReportStore()
        self._summarizer = summarizer

    def execute(self, arguments: dict) -> ToolExecutionResult:
        dataset_path = str(arguments.get("dataset_path", "evals/sample_eval_dataset.json")).strip()
        if not dataset_path:
            dataset_path = "evals/sample_eval_dataset.json"

        report = self._report_store.run(dataset_path)
        summary = report.get("summary", {})
        answer = self._summarize_report(report)
        return ToolExecutionResult(
            status="ok",
            answer=answer,
            result={
                "dataset_path": report.get("dataset_path", dataset_path),
                "report_path": report.get("report_path", ""),
                "generated_at_utc": report.get("generated_at_utc", ""),
                "sample_count": report.get("sample_count", 0),
                "summary": summary if isinstance(summary, dict) else {},
            },
        )

    def _summarize_report(self, report: dict) -> str:
        if self._summarizer is not None:
            try:
                return self._summarizer.summarize(report)
            except Exception:
                pass
        return _fallback_summary(report)


class GetEvaluationReportTool:
    name = "get_evaluation_report"
    metadata = ToolMetadata(
        name=name,
        description="Load the latest evaluation report or a specific report by path and summarize it.",
        arguments_schema={
            "report_path": {
                "type": "string",
                "required": False,
                "description": "Optional path to a specific evaluation report JSON file.",
            }
        },
        output_description="Returns report metadata, summary metrics, and the report records payload.",
        requires_confirmation=False,
        goal_tags=["quality", "validation", "benchmarking"],
        affects=["evaluation"],
        impact_summary="Reads the latest quality metrics so the admin can compare current performance before deciding on a change.",
        expected_tradeoffs=[
            "Read-only diagnostic; no system state is changed.",
        ],
        best_for=["quality monitoring", "before/after comparison", "decision support"],
        risk_level="low",
        typical_followups=["run_rag_evaluation"],
    )

    def __init__(
        self,
        report_store: EvaluationReportStore | None = None,
        summarizer: EvaluationReportSummarizer | None = None,
    ) -> None:
        self._report_store = report_store or EvaluationReportStore()
        self._summarizer = summarizer

    def execute(self, arguments: dict) -> ToolExecutionResult:
        report_path_raw = str(arguments.get("report_path", "")).strip()
        try:
            report = self._report_store.load_report(report_path_raw or None)
        except RuntimeError as exc:
            return ToolExecutionResult(
                status="error",
                answer=str(exc),
                result={},
            )
        summary = report.get("summary", {})
        answer = self._summarize_report(report)
        return ToolExecutionResult(
            status="ok",
            answer=answer,
            result={
                "report_path": report.get("report_path", ""),
                "dataset_path": report.get("dataset_path", ""),
                "generated_at_utc": report.get("generated_at_utc", ""),
                "sample_count": report.get("sample_count", 0),
                "summary": summary if isinstance(summary, dict) else {},
                "records": report.get("records", []),
            },
        )

    def _summarize_report(self, report: dict) -> str:
        if self._summarizer is not None:
            try:
                return self._summarizer.summarize(report)
            except Exception:
                pass
        return _fallback_summary(report)
