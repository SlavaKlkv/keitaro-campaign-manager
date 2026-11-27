"""Подключение к PostgreSQL, управление сессиями SQLAlchemy и запись журнала операций."""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Базовый класс декларативных моделей SQLAlchemy."""


def build_engine(database_url: str | None = None) -> Engine:
    """Создаёт SQLAlchemy Engine с учётом диалекта БД."""
    url = database_url or get_settings().database_url
    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session]:
    """Dependency FastAPI, выдающий сессию БД на время обработки запроса."""
    with SessionLocal() as session:
        yield session


def check_db_connection(db: Session | None = None) -> bool:
    """Проверяет доступность базы данных простым запросом SELECT 1."""
    try:
        if db is not None:
            db.execute(text("SELECT 1"))
            return True
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            return True
    except Exception:
        return False


def log_operation(
    db: Session,
    *,
    operation: str,
    resource_type: str,
    resource_id: int | None,
    summary: str,
    status: str = "success",
    details: dict[str, Any] | None = None,
) -> None:
    """Фиксирует операцию в таблице operation_logs без прерывания основного потока при сбое записи."""
    from app.models import OperationLog

    try:
        entry = OperationLog(
            operation=operation,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=summary,
            status=status,
            details=details,
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()
