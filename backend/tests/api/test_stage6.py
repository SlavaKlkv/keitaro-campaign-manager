"""API- и unit-тесты для Этапа 6: кэш справочников, DEMO_MODE, префикс/дефолты, внешние удаления, diff."""

from collections.abc import AsyncGenerator
from typing import Any

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import meta_cache
from app.config import Settings, get_settings
from app.deps import get_keitaro_client
from app.main import app
from app.models import OperationLog, StreamOfferSnapshot


class CountingFakeKeitaro:
    """Фейковый клиент для проверки кэша, внешних удалений и diff в журнале."""

    def __init__(self) -> None:
        self.base_url = "https://keitaro.example.com"
        self.meta_calls = 0
        self.stream_offers: list[dict[str, Any]] = [
            {"offer_id": 18001, "share": 50, "state": "active"},
            {"offer_id": 18002, "share": 50, "state": "active"},
        ]
        self.created_campaigns: list[dict[str, Any]] = []
        self.created_streams: list[dict[str, Any]] = []

    async def list_domains(self) -> list[dict[str, Any]]:
        self.meta_calls += 1
        return [
            {"id": 10, "name": "https://d1.example.com", "state": "active"},
            {"id": 12, "name": "https://d2.example.com", "state": "active"},
        ]

    async def list_groups(self, group_type: str = "campaigns") -> list[dict[str, Any]]:
        return [
            {"id": 20, "name": "Default", "type": group_type},
            {"id": 22, "name": "Configured Group", "type": group_type},
        ]

    async def list_traffic_sources(self) -> list[dict[str, Any]]:
        return [
            {"id": 30, "name": "Facebook", "state": "active"},
            {"id": 32, "name": "Configured Source", "state": "active"},
        ]

    async def list_offers(self) -> list[dict[str, Any]]:
        return [
            {"id": 18001, "name": "Offer Alpha", "state": "active", "country": ["RO"]},
            {"id": 18002, "name": "Offer Beta", "state": "active", "country": ["RO"]},
            {"id": 18003, "name": "Offer Gamma", "state": "active", "country": ["DE"]},
        ]

    async def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_campaigns.append(payload)
        return {"id": 888, **payload}

    async def create_stream(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_streams.append(payload)
        return {"id": 950 + len(self.created_streams), **payload}

    async def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        return {"id": campaign_id, "name": "Test Camp", "state": "active"}

    async def list_campaign_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        return [
            {
                "id": 502,
                "campaign_id": campaign_id,
                "name": "Офферы",
                "type": "default",
                "position": 2,
                "schema": "landings",
                "state": "active",
                "filters": [],
                "offers": list(self.stream_offers),
            }
        ]

    async def update_stream(self, stream_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.stream_offers = list(payload["offers"])
        return {"id": stream_id, **payload}


def test_meta_ttl_cache_and_force_refresh(api_client: TestClient) -> None:
    """GET /api/meta кэширует ответ по TTL и обновляется при ?refresh=true."""
    fake = CountingFakeKeitaro()

    async def _override() -> AsyncGenerator[CountingFakeKeitaro, None]:
        yield fake

    app.dependency_overrides[get_keitaro_client] = _override
    try:
        r1 = api_client.get("/api/meta")
        assert r1.status_code == 200
        assert r1.json()["cached"] is False
        assert fake.meta_calls == 1

        r2 = api_client.get("/api/meta")
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
        assert fake.meta_calls == 1

        r3 = api_client.get("/api/meta?refresh=true")
        assert r3.status_code == 200
        assert r3.json()["cached"] is False
        assert fake.meta_calls == 2
    finally:
        app.dependency_overrides.pop(get_keitaro_client, None)
        meta_cache.invalidate()


def test_prefix_safe_redirect_and_configured_defaults(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CAMPAIGN_NAME_PREFIX, SAFE_REDIRECT_URL и DEFAULT_*_ID применяются к /api/meta и созданию кампании."""
    custom_settings = Settings(
        keitaro_base_url="https://keitaro.example.com",
        keitaro_api_key="test-key",
        campaign_name_prefix="test_ivanov_",
        safe_redirect_url="https://safe.example.org/landing",
        default_domain_id=12,
        default_group_id=22,
        default_traffic_source_id=32,
        _env_file=None,
    )
    monkeypatch.setattr("app.routers.meta.get_settings", lambda: custom_settings)
    monkeypatch.setattr("app.routers.campaigns.get_settings", lambda: custom_settings)

    fake = CountingFakeKeitaro()

    async def _override() -> AsyncGenerator[CountingFakeKeitaro, None]:
        yield fake

    app.dependency_overrides[get_keitaro_client] = _override
    try:
        meta_resp = api_client.get("/api/meta")
        assert meta_resp.status_code == 200
        meta_json = meta_resp.json()
        assert meta_json["campaign_name_prefix"] == "test_ivanov_"
        assert meta_json["defaults"] == {
            "domain_id": 12,
            "group_id": 22,
            "traffic_source_id": 32,
        }

        cmp_resp = api_client.post(
            "/api/campaigns",
            json={
                "name": "ro_offer_1",
                "country_code": "RO",
                "offer_id": 18001,
                "domain_id": 12,
                "group_id": 22,
                "traffic_source_id": 32,
            },
        )
        assert cmp_resp.status_code == 201
        assert cmp_resp.json()["name"] == "test_ivanov_ro_offer_1"
        assert fake.created_campaigns[0]["name"] == "test_ivanov_ro_offer_1"
        assert fake.created_streams[0]["action_payload"] == "https://safe.example.org/landing"
    finally:
        app.dependency_overrides.pop(get_keitaro_client, None)


def test_external_offer_removal_detected_on_fetch(
    api_client: TestClient,
    db_session: Session,
) -> None:
    """Оффер, удалённый напрямую в Keitaro, возвращается со статусом removed (0%) и removed_externally=True."""
    fake = CountingFakeKeitaro()

    async def _override() -> AsyncGenerator[CountingFakeKeitaro, None]:
        yield fake

    app.dependency_overrides[get_keitaro_client] = _override
    try:
        first = api_client.get("/api/campaigns/55/streams")
        assert first.status_code == 200
        assert len(first.json()["streams"][0]["offers"]) == 2

        snaps = db_session.scalars(select(StreamOfferSnapshot)).all()
        assert len(snaps) == 2

        # Имитируем удаление оффера 18002 напрямую в интерфейсе Keitaro
        fake.stream_offers = [{"offer_id": 18001, "share": 100, "state": "active"}]

        second = api_client.get("/api/campaigns/55/streams")
        assert second.status_code == 200
        offers = second.json()["streams"][0]["offers"]
        assert len(offers) == 2
        removed = next(o for o in offers if o["offer_id"] == 18002)
        assert removed["state"] == "removed"
        assert removed["share"] == 0
        assert removed["removed_externally"] is True
        assert removed["name"] == "Offer Beta"
    finally:
        app.dependency_overrides.pop(get_keitaro_client, None)


def test_update_stream_offers_records_before_after_diff_and_log_filters(
    api_client: TestClient,
) -> None:
    """PUSH TO KT записывает diff «было → стало» в operation_logs, а GET /api/logs поддерживает фильтры."""
    fake = CountingFakeKeitaro()

    async def _override() -> AsyncGenerator[CountingFakeKeitaro, None]:
        yield fake

    app.dependency_overrides[get_keitaro_client] = _override
    try:
        resp = api_client.put(
            "/api/campaigns/55/streams/502/offers",
            json={
                "offers": [
                    {"offer_id": 18001, "share": 70, "state": "active"},
                    {"offer_id": 18003, "share": 30, "state": "active"},
                ]
            },
        )
        assert resp.status_code == 200

        logs_resp = api_client.get("/api/logs?operation=stream.offers.update&resource_id=502")
        assert logs_resp.status_code == 200
        logs = logs_resp.json()
        assert len(logs) == 1
        details = logs[0]["details"]
        assert details["campaign_id"] == 55
        assert details["stream_id"] == 502
        assert len(details["before"]) == 2
        assert len(details["after"]) == 2
        diff_by_id = {d["offer_id"]: d for d in details["diff"]}
        assert diff_by_id[18001]["change"] == "changed"
        assert diff_by_id[18001]["before_share"] == 50
        assert diff_by_id[18001]["after_share"] == 70
        assert diff_by_id[18002]["change"] == "removed"
        assert diff_by_id[18003]["change"] == "added"
        assert diff_by_id[18003]["after_share"] == 30
    finally:
        app.dependency_overrides.pop(get_keitaro_client, None)


def test_demo_mode_works_without_keitaro_api_key(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """При DEMO_MODE=true API работает без KEITARO_API_KEY, включая создание и редактирование."""
    demo_settings = Settings(
        keitaro_base_url="",
        keitaro_api_key="",
        demo_mode=True,
        _env_file=None,
    )
    monkeypatch.setattr("app.deps.get_settings", lambda: demo_settings)
    monkeypatch.setattr("app.routers.meta.get_settings", lambda: demo_settings)
    monkeypatch.setattr("app.routers.health.get_settings", lambda: demo_settings)
    monkeypatch.setattr("app.routers.campaigns.get_settings", lambda: demo_settings)

    health = api_client.get("/health")
    assert health.status_code == 200
    assert health.json()["demo_mode"] is True

    meta = api_client.get("/api/meta")
    assert meta.status_code == 200
    assert meta.json()["demo_mode"] is True
    assert len(meta.json()["offers"]) >= 5

    campaigns = api_client.get("/api/campaigns")
    assert campaigns.status_code == 200
    assert len(campaigns.json()) >= 3

    created = api_client.post(
        "/api/campaigns",
        json={
            "name": "Demo Flow Test",
            "country_code": "DE",
            "offer_id": 18004,
            "domain_id": 10,
            "group_id": 21,
            "traffic_source_id": 31,
        },
    )
    assert created.status_code == 201
    new_id = created.json()["id"]
    streams = api_client.get(f"/api/campaigns/{new_id}/streams")
    assert streams.status_code == 200
    assert len(streams.json()["streams"]) == 2

    # Сбрасываем кэш settings на всякий случай
    get_settings.cache_clear()
