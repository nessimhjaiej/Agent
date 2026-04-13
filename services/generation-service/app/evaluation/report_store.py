from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class EvaluationReportSummary:
    report_id: str
    filename: str
    generated_at_utc: str
    sample_count: int
    summary: dict[str, float]
    dataset_path: str


def list_reports(reports_dir: Path) -> list[EvaluationReportSummary]:
    if not reports_dir.exists():
        return []

    summaries: list[EvaluationReportSummary] = []
    for path in sorted(reports_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summaries.append(_to_summary(path, payload))
    return summaries


def load_report(reports_dir: Path, report_id: str) -> dict:
    normalized = report_id.strip()
    if not normalized:
        raise ValueError("report_id is required")

    filename = normalized if normalized.endswith(".json") else f"{normalized}.json"
    report_path = reports_dir / filename
    if not report_path.exists():
        raise FileNotFoundError(f"Evaluation report not found: {filename}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def compare_reports(left: dict, right: dict) -> dict[str, dict[str, float | None]]:
    left_summary = left.get("summary", {})
    right_summary = right.get("summary", {})
    if not isinstance(left_summary, dict) or not isinstance(right_summary, dict):
        raise ValueError("Evaluation reports must contain summary objects")

    metrics = sorted(set(left_summary) | set(right_summary))
    comparison: dict[str, dict[str, float | None]] = {}
    for metric in metrics:
        left_value = _as_float_or_none(left_summary.get(metric))
        right_value = _as_float_or_none(right_summary.get(metric))
        delta = None
        if left_value is not None and right_value is not None:
            delta = round(right_value - left_value, 6)
        comparison[metric] = {
            "baseline": left_value,
            "candidate": right_value,
            "delta": delta,
        }
    return comparison


def _to_summary(path: Path, payload: dict) -> EvaluationReportSummary:
    generated_at = str(payload.get("generated_at_utc") or "")
    sample_count = payload.get("sample_count", 0)
    summary = payload.get("summary", {})
    dataset_path = str(payload.get("dataset_path") or "")
    return EvaluationReportSummary(
        report_id=path.stem,
        filename=path.name,
        generated_at_utc=generated_at,
        sample_count=int(sample_count) if isinstance(sample_count, (int, float)) else 0,
        summary={k: float(v) for k, v in summary.items() if isinstance(v, (int, float))},
        dataset_path=dataset_path,
    )


def _as_float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
