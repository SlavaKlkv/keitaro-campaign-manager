"""Точка входа FastAPI-приложения Keitaro Campaign Manager."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers.health import router as health_router


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
    return application


app = create_app()
