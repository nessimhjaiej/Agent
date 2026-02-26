from fastapi import FastAPI

from app.config import Settings
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router


def create_app() -> FastAPI:
    settings = Settings.from_env()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    return app


app = create_app()
