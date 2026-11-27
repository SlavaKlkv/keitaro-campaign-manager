"""Эндпоинт проверки работоспособности сервиса и подключения к БД."""

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import check_db_connection, get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Возвращает статус приложения, состояние соединения с PostgreSQL и режим DEMO_MODE."""
    settings = get_settings()
    db_ok = check_db_connection(db)
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unavailable", "demo_mode": settings.demo_mode}
    return {"status": "ok", "database": "ok", "demo_mode": settings.demo_mode}
