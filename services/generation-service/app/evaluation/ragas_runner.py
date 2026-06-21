from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from app.schemas import AskRequest
from app.service import GenerationService


@dataclass(slots=True)
class EvaluationSample:
    question: str
    reference: str
    mode: str = "hybrid"
    top_k_retrieve: int | None = None
    top_k_return: int | None = None
    filters: dict | None = None


class RagasEvaluationRunner:
    def __init__(
        self,
        service: GenerationService | None = None,
        reports_dir: Path | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = service or GenerationService()
        self._root_dir = Path(__file__).resolve().parents[2]
        self._reports_dir = reports_dir or (self._root_dir / "evaluation_reports")
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

    @staticmethod
    def load_dataset(path: Path) -> list[EvaluationSample]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Dataset must be a JSON array")

        samples: list[EvaluationSample] = []
        for idx, row in enumerate(raw):
            if not isinstance(row, dict):
                raise ValueError(f"Dataset row {idx} must be an object")
            question = str(row.get("question", "")).strip()
            reference = str(row.get("reference", "")).strip()
            if not question:
                raise ValueError(f"Dataset row {idx} is missing 'question'")
            if not reference:
                raise ValueError(f"Dataset row {idx} is missing 'reference'")
            samples.append(
                EvaluationSample(
                    question=question,
                    reference=reference,
                    mode=str(row.get("mode", "hybrid")),
                    top_k_retrieve=row.get("top_k_retrieve"),
                    top_k_return=row.get("top_k_return"),
                    filters=row.get("filters") if isinstance(row.get("filters"), dict) else None,
                )
            )
        return samples

    def build_ragas_rows(self, samples: list[EvaluationSample]) -> list[dict]:
        rows: list[dict] = []
        for sample in samples:
            response = self._service.ask(
                AskRequest(
                    query=sample.question,
                    mode=sample.mode,
                    top_k_retrieve=sample.top_k_retrieve,
                    top_k_return=sample.top_k_return,
                    filters=sample.filters or {},
                )
            )
            rows.append(
                {
                    "user_input": sample.question,
                    "response": response.answer,
                    "reference": sample.reference,
                    "retrieved_contexts": [citation.chunk_text for citation in response.citations],
                }
            )
        return rows

    @staticmethod
    def _ensure_openai_api_key() -> None:
        if not os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_KEY"):
            os.environ["OPENAI_API_KEY"] = str(os.getenv("OPENAI_KEY"))
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Set OPENAI_API_KEY (or OPENAI_KEY) before running Ragas evaluation.")

    @staticmethod
    def _build_eval_llm():
        model_name = os.getenv("RAGAS_EVAL_MODEL", os.getenv("GENERATION_MODEL", "gpt-4o-mini"))
        api_key = os.getenv("OPENAI_API_KEY")

        # Modern ragas (>=0.3) llm_factory takes an explicit OpenAI client.
        try:
            from openai import OpenAI
            from ragas.llms import llm_factory

            return llm_factory(
                model=model_name,
                provider="openai",
                client=OpenAI(api_key=api_key),
                temperature=0.0,
            )
        except TypeError:
            # Older ragas (0.2.x) exposes a different llm_factory signature;
            # wrap a LangChain chat model instead, which is stable across versions.
            from langchain_openai import ChatOpenAI
            from ragas.llms import LangchainLLMWrapper

            return LangchainLLMWrapper(
                ChatOpenAI(model=model_name, api_key=api_key, temperature=0.0)
            )

    @staticmethod
    def run_ragas(rows: list[dict]) -> tuple[dict[str, float], list[dict]]:
        RagasEvaluationRunner._ensure_openai_api_key()

        try:
            from ragas import EvaluationDataset, evaluate
            from ragas.metrics._context_recall import ContextRecall
            from ragas.metrics._factual_correctness import FactualCorrectness
            from ragas.metrics._faithfulness import Faithfulness
        except ImportError as exc:
            raise RuntimeError(
                "Ragas dependencies are missing or incompatible. Install from generation-service/requirements.txt."
            ) from exc

        eval_llm = RagasEvaluationRunner._build_eval_llm()
        dataset = EvaluationDataset.from_list(rows)
        result = evaluate(
            dataset=dataset,
            llm=eval_llm,
            metrics=[
                ContextRecall(),
                Faithfulness(),
                FactualCorrectness(),
            ],
        )
        frame = result.to_pandas()

        summary: dict[str, float] = {}
        for column in frame.columns:
            if column in {"user_input", "response", "reference", "retrieved_contexts"}:
                continue
            series = frame[column]
            if hasattr(series, "dtype") and str(series.dtype).startswith(("float", "int")):
                value = float(series.mean())
                if value == value:  # NaN check
                    summary[column] = round(value, 6)

        return summary, frame.to_dict(orient="records")

    def write_report(
        self,
        dataset_path: Path,
        sample_count: int,
        summary: dict[str, float],
        records: list[dict],
    ) -> Path:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = self._now_fn().astimezone(UTC).strftime("%Y%m%d_%H%M%S")
        output_path = self._reports_dir / f"ragas_report_{timestamp}.json"
        payload = {
            "generated_at_utc": self._now_fn().astimezone(UTC).isoformat(),
            "dataset_path": str(dataset_path),
            "sample_count": sample_count,
            "summary": summary,
            "records": records,
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path

    def run(self, dataset_path: Path) -> Path:
        self._ensure_openai_api_key()
        samples = self.load_dataset(dataset_path)
        rows = self.build_ragas_rows(samples)
        summary, records = self.run_ragas(rows)
        return self.write_report(
            dataset_path=dataset_path,
            sample_count=len(samples),
            summary=summary,
            records=records,
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Ragas evaluation against generation-service and write a dated report."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/sample_eval_dataset.json"),
        help="Path to JSON dataset. Each row needs: question, reference.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runner = RagasEvaluationRunner()
    report_path = runner.run(args.dataset)
    print(f"Ragas report written to: {report_path}")


if __name__ == "__main__":
    main()
