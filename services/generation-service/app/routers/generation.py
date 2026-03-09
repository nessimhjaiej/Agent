from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.errors import GenerationProviderError, GenerationServiceError, GenerationValidationError
from app.schemas import AskRequest, AskResponse, ChatRequest, ChatResponse, TranscriptionResponse
from app.service import GenerationService


router = APIRouter(prefix="/generation", tags=["generation"])


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
