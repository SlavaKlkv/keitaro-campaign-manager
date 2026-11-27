"""Зависимости FastAPI для получения клиента Keitaro."""

from collections.abc import AsyncGenerator

from fastapi import HTTPException, status

from app.config import get_settings
from app.demo_keitaro import DemoKeitaroClient, get_demo_keitaro_client
from app.keitaro import KeitaroClient


async def get_keitaro_client() -> AsyncGenerator[KeitaroClient | DemoKeitaroClient, None]:
    """Создаёт и корректно закрывает клиент Keitaro (или DemoKeitaroClient в DEMO_MODE)."""
    settings = get_settings()
    if settings.demo_mode:
        yield get_demo_keitaro_client()
        return

    if not settings.keitaro_base_url or not settings.keitaro_api_key.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Учётные данные Keitaro (KEITARO_BASE_URL / KEITARO_API_KEY) не настроены",
        )
    async with KeitaroClient(settings) as client:
        yield client
