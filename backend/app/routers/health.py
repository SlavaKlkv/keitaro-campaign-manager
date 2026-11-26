"""Эндпоинт проверки работоспособности сервиса и подключения к БД."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database import check_db_connection, get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    """Возвращает статус приложения и состояние соединения с PostgreSQL."""
    db_ok = check_db_connection(db)
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}
