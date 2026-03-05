from fastapi import FastAPI

from app.config import Settings
from app.routers.health import router as health_router
from app.routers.ingestion import router as ingestion_router


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    app = FastAPI(title=runtime_settings.app_name, version=runtime_settings.app_version)
    app.include_router(health_router)
    app.include_router(ingestion_router)
    return app


app = create_app()

