"""API-тесты справочников (/api/meta), создания кампаний и журнала операций."""

from collections.abc import AsyncGenerator, Iterator
from typing import Any

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_keitaro_client
from app.keitaro import KeitaroError
from app.main import app
from app.models import OperationLog


class FakeKeitaroClient:
    """Поддельный клиент Keitaro для изолированных API-тестов."""

    def __init__(self, *, fail_second_stream: bool = False) -> None:
        self.fail_second_stream = fail_second_stream
        self.created_campaigns: list[dict[str, Any]] = []
        self.created_streams: list[dict[str, Any]] = []
        self.disabled_campaigns: list[int] = []
        self.deleted_campaigns: list[int] = []

    async def list_domains(self) -> list[dict[str, Any]]:
        return [
            {"id": 10, "name": "https://in.posdk.xyz/", "state": "active", "is_ssl": True},
            {"id": 11, "name": "deleted.xyz", "state": "deleted"},
        ]

    async def list_groups(self, group_type: str = "campaigns") -> list[dict[str, Any]]:
        return [
            {"id": 20, "name": "Default", "type": group_type},
            {"id": 21, "name": "FORTESTS", "type": group_type},
        ]

    async def list_traffic_sources(self) -> list[dict[str, Any]]:
        return [
            {"id": 30, "name": "Facebook", "state": "active"},
            {"id": 31, "name": "FORTESTS", "state": "active"},
        ]

    async def list_offers(self) -> list[dict[str, Any]]:
        return [
            {"id": 18001, "name": "18001 Offer Alpha", "state": "active", "country": ["AU"]},
            {"id": 18002, "name": "18002 Offer Beta", "state": "active", "country": ["RO"]},
        ]

    async def list_campaigns(self, limit: int | None = None, offset: int | None = None) -> list[dict[str, Any]]:
        return [
            {
                "id": 101,
                "name": "Existing Campaign",
                "alias": "existing-cmp",
                "state": "active",
                "domain_id": 10,
                "domain": "https://in.posdk.xyz/",
                "group_id": 21,
                "group": "FORTESTS",
                "traffic_source_id": 31,
                "type": "position",
                "cost_type": "CPC",
            }
        ]

    async def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_campaigns.append(payload)
        return {"id": 777, **payload}

    async def create_stream(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.fail_second_stream and len(self.created_streams) == 1:
            raise KeitaroError("Stream creation failed", status_code=502)
        self.created_streams.append(payload)
        return {"id": 900 + len(self.created_streams), **payload}

    async def disable_campaign(self, campaign_id: int) -> dict[str, Any]:
        self.disabled_campaigns.append(campaign_id)
        return {"id": campaign_id, "state": "disabled"}

    async def delete_campaign(self, campaign_id: int) -> None:
        self.deleted_campaigns.append(campaign_id)


@pytest.fixture()
def fake_keitaro() -> FakeKeitaroClient:
    return FakeKeitaroClient()


@pytest.fixture()
def client_with_fake_kt(
    api_client: TestClient,
    fake_keitaro: FakeKeitaroClient,
) -> Iterator[TestClient]:
    async def _override() -> AsyncGenerator[FakeKeitaroClient]:
        yield fake_keitaro

    app.dependency_overrides[get_keitaro_client] = _override
    yield api_client
    app.dependency_overrides.pop(get_keitaro_client, None)


def test_get_meta_returns_catalogs_and_defaults(client_with_fake_kt: TestClient) -> None:
    """Эндпоинт /api/meta возвращает домены, группы, источники, офферы и дефолты."""
    resp = client_with_fake_kt.get("/api/meta")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["domains"]) == 1
    assert data["defaults"]["domain_id"] == 10
    assert data["defaults"]["group_id"] == 21
    assert data["defaults"]["traffic_source_id"] == 31
    assert len(data["offers"]) == 2


def test_create_campaign_creates_two_streams_and_logs_operation(
    client_with_fake_kt: TestClient,
    fake_keitaro: FakeKeitaroClient,
    db_session: Session,
) -> None:
    """POST /api/campaigns создаёт кампанию с ротацией по позиции, CPC, 2 потоками и пишет лог в БД."""
    resp = client_with_fake_kt.post(
        "/api/campaigns",
        json={
            "name": "Test AU Campaign",
            "country_code": "au",
            "offer_id": 18001,
            "domain_id": 10,
            "group_id": 21,
            "traffic_source_id": 31,
            "alias": "test-au-1",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == 777
    assert body["country_code"] == "AU"
    assert body["streams_created"] == 2
    assert body["tracking_url"] == "https://in.posdk.xyz/test-au-1"

    assert len(fake_keitaro.created_campaigns) == 1
    cmp_payload = fake_keitaro.created_campaigns[0]
    assert cmp_payload["type"] == "position"
    assert cmp_payload["cost_type"] == "CPC"

    assert len(fake_keitaro.created_streams) == 2
    flow1, flow2 = fake_keitaro.created_streams
    assert flow1["schema"] == "redirect"
    assert flow1["action_payload"] == "https://google.com"
    assert flow1["filters"] == [{"name": "country", "mode": "accept", "payload": ["AU"]}]
    assert flow2["schema"] == "landings"
    assert flow2["offers"] == [{"offer_id": 18001, "share": 100, "state": "active"}]

    logs = db_session.scalars(select(OperationLog)).all()
    assert len(logs) == 1
    assert logs[0].operation == "campaign.create"
    assert logs[0].status == "success"
    assert logs[0].resource_id == 777


def test_create_campaign_rejects_unknown_offer(client_with_fake_kt: TestClient) -> None:
    """Неизвестный offer_id возвращает 422."""
    resp = client_with_fake_kt.post(
        "/api/campaigns",
        json={
            "name": "Bad Offer",
            "country_code": "DE",
            "offer_id": 999999,
            "domain_id": 10,
            "group_id": 21,
            "traffic_source_id": 31,
        },
    )
    assert resp.status_code == 422


def test_create_campaign_disables_campaign_on_stream_failure(
    api_client: TestClient,
    db_session: Session,
) -> None:
    """При ошибке создания второго потока кампания отключается и пишется error-лог."""
    broken = FakeKeitaroClient(fail_second_stream=True)

    async def _override() -> AsyncGenerator[FakeKeitaroClient]:
        yield broken

    app.dependency_overrides[get_keitaro_client] = _override
    try:
        resp = api_client.post(
            "/api/campaigns",
            json={
                "name": "Partial Fail",
                "country_code": "RO",
                "offer_id": 18001,
                "domain_id": 10,
                "group_id": 21,
                "traffic_source_id": 31,
            },
        )
    finally:
        app.dependency_overrides.pop(get_keitaro_client, None)

    assert resp.status_code == 502
    assert broken.disabled_campaigns == [777]
    logs = db_session.scalars(select(OperationLog)).all()
    assert len(logs) == 1
    assert logs[0].status == "error"
