"""Общие фикстуры для unit- и API-тестов."""

from collections.abc import Generator

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.cache import meta_cache
from app.database import Base, get_db
from app.demo_keitaro import reset_demo_keitaro_client
from app.main import app


@pytest.fixture(autouse=True)
def reset_runtime_caches() -> Generator[None, None, None]:
    """Очищает in-memory кэши и demo-клиент между тестами."""
    meta_cache.invalidate()
    reset_demo_keitaro_client()
    yield
    meta_cache.invalidate()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Изолированная in-memory SQLite БД на каждый тест для быстрой проверки без живого Postgres."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def api_client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient с подменённой зависимостью get_db."""

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
