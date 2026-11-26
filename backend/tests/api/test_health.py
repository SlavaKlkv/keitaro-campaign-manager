"""Smoke-тесты эндпоинта /health."""

from fastapi.testclient import TestClient


def test_health_returns_ok_when_db_is_available(api_client: TestClient) -> None:
    """Эндпоинт /health возвращает 200 и статус ok при доступной БД."""
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_returns_503_when_db_check_fails(api_client: TestClient, monkeypatch) -> None:
    """При недоступной БД /health возвращает 503 degraded."""
    monkeypatch.setattr("app.routers.health.check_db_connection", lambda db=None: False)
    response = api_client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
