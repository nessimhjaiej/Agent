from fastapi import APIRouter, HTTPException

from app.errors import GenerationProviderError, GenerationServiceError, GenerationValidationError
from app.schemas import AskRequest, AskResponse, ChatRequest, ChatResponse
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
