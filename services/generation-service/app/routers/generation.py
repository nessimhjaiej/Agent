from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import Settings
from app.evaluation.ragas_runner import RagasEvaluationRunner
from app.evaluation.report_store import compare_reports, list_reports, load_report
from app.errors import GenerationProviderError, GenerationServiceError, GenerationValidationError
from app.schemas import (
    AskRequest,
    AskResponse,
    ChatRequest,
    ChatResponse,
    EvaluationCompareRequest,
    EvaluationCompareResponse,
    EvaluationListResponse,
    EvaluationMetricDelta,
    EvaluationReportSummaryResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
    TranscriptionResponse,
)
from app.service import GenerationService


router = APIRouter(prefix="/generation", tags=["generation"])


def _reports_dir() -> Path:
    return Path(Settings.from_env().evaluation_reports_dir)


def _report_summary_response(report) -> EvaluationReportSummaryResponse:  # noqa: ANN001
    return EvaluationReportSummaryResponse(
        report_id=report.report_id,
        filename=report.filename,
        generated_at_utc=report.generated_at_utc,
        sample_count=report.sample_count,
        dataset_path=report.dataset_path,
        summary=report.summary,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        service = GenerationService()
        return service.chat(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GenerationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GenerationProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except GenerationServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    try:
        service = GenerationService()
        return service.ask(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GenerationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GenerationProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except GenerationServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    prompt: str | None = Form(default=None),
) -> TranscriptionResponse:
    try:
        service = GenerationService()
        content = await file.read()
        return service.transcribe(
            filename=file.filename or "audio",
            content=content,
            content_type=file.content_type,
            language=language,
            prompt=prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GenerationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GenerationProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except GenerationServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/evaluations/run", response_model=EvaluationRunResponse)
def run_evaluation(payload: EvaluationRunRequest) -> EvaluationRunResponse:
    settings = Settings.from_env()
    dataset_path = Path(payload.dataset_path)
    if not dataset_path.is_absolute():
        dataset_path = settings.project_root / dataset_path

    try:
        runner = RagasEvaluationRunner(reports_dir=Path(settings.evaluation_reports_dir))
        report_path = runner.run(dataset_path)
        report = next(
            item
            for item in list_reports(Path(settings.evaluation_reports_dir))
            if item.filename == report_path.name
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StopIteration as exc:
        raise HTTPException(status_code=500, detail="Evaluation report was written but could not be reloaded") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return EvaluationRunResponse(status="ok", report=_report_summary_response(report))


@router.get("/evaluations", response_model=EvaluationListResponse)
def get_evaluations() -> EvaluationListResponse:
    reports = [_report_summary_response(item) for item in list_reports(_reports_dir())]
    return EvaluationListResponse(status="ok", reports=reports)


@router.post("/evaluations/compare", response_model=EvaluationCompareResponse)
def compare_evaluations(payload: EvaluationCompareRequest) -> EvaluationCompareResponse:
    try:
        reports_dir = _reports_dir()
        baseline = load_report(reports_dir, payload.baseline_report_id)
        candidate = load_report(reports_dir, payload.candidate_report_id)
        comparison = compare_reports(baseline, candidate)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return EvaluationCompareResponse(
        status="ok",
        baseline_report_id=payload.baseline_report_id,
        candidate_report_id=payload.candidate_report_id,
        metrics={
            metric: EvaluationMetricDelta(
                baseline=values["baseline"],
                candidate=values["candidate"],
                delta=values["delta"],
            )
            for metric, values in comparison.items()
        },
    )
