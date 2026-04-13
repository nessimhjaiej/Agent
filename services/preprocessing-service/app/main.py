from fastapi import FastAPI

from app.config import Settings
from app.middleware.security import RateLimitMiddleware, RequestSizeLimitMiddleware
from app.routers.health import router as health_router
from app.routers.preprocessing import router as preprocessing_router


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    app = FastAPI(
        title=runtime_settings.app_name,
        version=runtime_settings.app_version,
    )
    app.state.settings = runtime_settings
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_request_size_bytes=runtime_settings.max_request_size_bytes,
    )
    app.add_middleware(
        RateLimitMiddleware,
        limit=runtime_settings.rate_limit_requests,
        window_seconds=runtime_settings.rate_limit_window_seconds,
    )
    app.include_router(health_router)
    app.include_router(preprocessing_router)
    return app


app = create_app()
