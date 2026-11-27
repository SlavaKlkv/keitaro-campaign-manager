"""Точка входа FastAPI-приложения Keitaro Campaign Manager."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers.bulk import router as bulk_router
from app.routers.campaigns import router as campaigns_router
from app.routers.health import router as health_router
from app.routers.logs import router as logs_router
from app.routers.meta import router as meta_router


def create_app() -> FastAPI:
    """Создаёт и конфигурирует экземпляр FastAPI."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="API-обёртка для создания кампаний и управления потоками/офферами Keitaro",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router)
    application.include_router(meta_router)
    application.include_router(bulk_router)
    application.include_router(campaigns_router)
    application.include_router(logs_router)
    return application


app = create_app()
