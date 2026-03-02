from fastapi import APIRouter

from app.config import Settings
from app.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns service status, name, and version.",
)
def health() -> HealthResponse:
    settings = Settings.from_env()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )
