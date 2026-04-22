from fastapi import FastAPI

from app.config import Settings
from app.database import SecurityDatabase
from app.routers.health import router as health_router
from app.routers.security import router as security_router
from app.service import SecurityService


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    app = FastAPI(title=runtime_settings.app_name, version=runtime_settings.app_version)
    app.state.security_service = SecurityService(
        recent_alert_limit=runtime_settings.recent_alert_limit,
        database=SecurityDatabase(runtime_settings),
    )
    app.include_router(health_router)
    app.include_router(security_router)
    return app


app = create_app()
