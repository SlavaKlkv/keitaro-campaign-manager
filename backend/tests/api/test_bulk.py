"""API-тесты массовых операций (Этап 8): Bulk Create, Clone to GEOs, Bulk Offer Replace."""

from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_keitaro_client
from app.main import app
from app.models import OperationLog


class FakeBulkKeitaro:
    """In-memory фейк Keitaro для проверки массовых операций."""

    def __init__(self) -> None:
        self.base_url = "https://keitaro.example.com"
        self._next_cid = 200
        self._next_sid = 600
        self.campaigns: dict[int, dict[str, Any]] = {
            101: {
                "id": 101,
                "name": "Base_RO",
                "alias": "base-ro",
                "state": "active",
                "domain_id": 10,
                "domain": "https://d1.example.com",
                "group_id": 21,
                "traffic_source_id": 31,
                "type": "position",
                "cost_type": "CPC",
            },
            102: {
                "id": 102,
                "name": "Split_DE",
                "alias": "split-de",
                "state": "active",
                "domain_id": 10,
                "domain": "https://d1.example.com",
                "group_id": 21,
                "traffic_source_id": 31,
                "type": "position",
                "cost_type": "CPC",
            },
        }
        self.streams: dict[int, dict[str, Any]] = {
            501: {
                "id": 501,
                "campaign_id": 101,
                "name": "Geo RO",
                "type": "regular",
                "position": 1,
                "schema": "redirect",
                "action_type": "http",
                "action_payload": "https://google.com",
                "state": "active",
                "filters": [{"name": "country", "mode": "accept", "payload": ["RO"]}],
                "offers": [],
            },
            502: {
                "id": 502,
                "campaign_id": 101,
                "name": "Офферы",
                "type": "default",
                "position": 2,
                "schema": "landings",
                "action_type": "do_nothing",
                "state": "active",
                "filters": [],
                "offers": [
                    {"offer_id": 18001, "share": 60, "state": "active"},
                    {"offer_id": 18002, "share": 40, "state": "active"},
                ],
            },
            503: {
                "id": 503,
                "campaign_id": 102,
                "name": "Офферы DE",
                "type": "default",
                "position": 1,
                "schema": "landings",
                "action_type": "do_nothing",
                "state": "active",
                "filters": [],
                "offers": [
                    {"offer_id": 18001, "share": 100, "state": "active"},
                ],
            },
        }

    async def list_domains(self) -> list[dict[str, Any]]:
        return [{"id": 10, "name": "https://d1.example.com", "state": "active"}]

    async def list_groups(self, group_type: str = "campaigns") -> list[dict[str, Any]]:
        return [{"id": 21, "name": "FORTESTS", "type": group_type}]

    async def list_traffic_sources(self) -> list[dict[str, Any]]:
        return [{"id": 31, "name": "FORTESTS", "state": "active"}]

    async def list_offers(self) -> list[dict[str, Any]]:
        return [
            {"id": 18001, "name": "Offer 18001", "state": "active"},
            {"id": 18002, "name": "Offer 18002", "state": "active"},
            {"id": 18003, "name": "Offer 18003", "state": "active"},
        ]

    async def list_campaigns(self, limit: int | None = None, offset: int | None = None) -> list[dict[str, Any]]:
        return [deepcopy(c) for c in self.campaigns.values()]

    async def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        return deepcopy(self.campaigns[campaign_id])

    async def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        cid = self._next_cid
        self._next_cid += 1
        rec = {"id": cid, **deepcopy(payload)}
        self.campaigns[cid] = rec
        return deepcopy(rec)

    async def list_campaign_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        return [deepcopy(s) for s in self.streams.values() if s["campaign_id"] == campaign_id]

    async def create_stream(self, payload: dict[str, Any]) -> dict[str, Any]:
        sid = self._next_sid
        self._next_sid += 1
        rec = {"id": sid, **deepcopy(payload)}
        self.streams[sid] = rec
        return deepcopy(rec)

    async def update_stream(self, stream_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.streams[stream_id].update(deepcopy(payload))
        return deepcopy(self.streams[stream_id])


def test_bulk_create_handles_valid_and_invalid_rows_independently(
    api_client: TestClient,
    db_session: Session,
) -> None:
    """POST /api/campaigns/bulk создаёт валидные строки и фиксирует ошибки по невалидным."""
    fake = FakeBulkKeitaro()

    async def _override() -> AsyncGenerator[FakeBulkKeitaro, None]:
        yield fake

    app.dependency_overrides[get_keitaro_client] = _override
    try:
        resp = api_client.post(
            "/api/campaigns/bulk",
            json={
                "domain_id": 10,
                "group_id": 21,
                "traffic_source_id": 31,
                "items": [
                    {"name": "Camp DE", "country_code": "de", "offer_id": 18001},
                    {"name": "Camp Bad", "country_code": "FR", "offer_id": 999999},
                    {"name": "Camp ES", "country_code": "es", "offer_id": 18003},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["succeeded"] == 2
        assert data["failed"] == 1
        assert data["results"][0]["status"] == "success"
        assert data["results"][0]["campaign_id"] == 200
        assert data["results"][1]["status"] == "error"
        assert data["results"][2]["status"] == "success"

        logs = db_session.scalars(select(OperationLog)).all()
        assert len(logs) == 3
    finally:
        app.dependency_overrides.pop(get_keitaro_client, None)


def test_clone_campaign_to_geos_replaces_country_filter_and_copies_offers(
    api_client: TestClient,
) -> None:
    """POST /api/campaigns/{id}/clone-geos клонирует кампанию, заменяя GEO в Flow 1."""
    fake = FakeBulkKeitaro()

    async def _override() -> AsyncGenerator[FakeBulkKeitaro, None]:
        yield fake

    app.dependency_overrides[get_keitaro_client] = _override
    try:
        resp = api_client.post(
            "/api/campaigns/101/clone-geos",
            json={"country_codes": ["de", "fr", "DE"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert [r["country_code"] for r in data["results"]] == ["DE", "FR"]
        assert data["results"][0]["name"] == "Base_RO_DE"

        de_cid = data["results"][0]["campaign_id"]
        de_streams = [s for s in fake.streams.values() if s["campaign_id"] == de_cid]
        assert len(de_streams) == 2
        assert de_streams[0]["filters"] == [{"name": "country", "mode": "accept", "payload": ["DE"]}]
        assert de_streams[1]["offers"] == [
            {"offer_id": 18001, "share": 60, "state": "active"},
            {"offer_id": 18002, "share": 40, "state": "active"},
        ]
    finally:
        app.dependency_overrides.pop(get_keitaro_client, None)


def test_bulk_offer_replace_preview_and_apply_for_replace_and_disable(
    api_client: TestClient,
    db_session: Session,
) -> None:
    """Предпросмотр и применение замены/отключения оффера пересчитывают доли до 100% и пишут журнал."""
    fake = FakeBulkKeitaro()

    async def _override() -> AsyncGenerator[FakeBulkKeitaro, None]:
        yield fake

    app.dependency_overrides[get_keitaro_client] = _override
    try:
        # 1) Отключение 18001: поток 502 пересчитывается (18002 -> 100%), а поток 503 пропускается
        preview_disable = api_client.post(
            "/api/campaigns/bulk-offer-replace/preview",
            json={"source_offer_id": 18001, "target_offer_id": None},
        )
        assert preview_disable.status_code == 200
        pd = preview_disable.json()
        assert len(pd["affected_streams"]) == 1
        assert pd["affected_streams"][0]["stream_id"] == 502
        assert pd["affected_streams"][0]["after"] == [
            {"offer_id": 18002, "name": "Offer 18002", "share": 100, "state": "active"}
        ]
        assert len(pd["skipped_streams"]) == 1
        assert pd["skipped_streams"][0]["stream_id"] == 503

        # 2) Замена 18001 -> 18003 затрагивает оба потока (502 и 503)
        apply_replace = api_client.post(
            "/api/campaigns/bulk-offer-replace/apply",
            json={"source_offer_id": 18001, "target_offer_id": 18003},
        )
        assert apply_replace.status_code == 200
        ar = apply_replace.json()
        assert ar["succeeded"] == 2
        assert ar["failed"] == 0

        assert fake.streams[502]["offers"] == [
            {"offer_id": 18003, "share": 60, "state": "active"},
            {"offer_id": 18002, "share": 40, "state": "active"},
        ]
        assert fake.streams[503]["offers"] == [
            {"offer_id": 18003, "share": 100, "state": "active"},
        ]

        logs = db_session.scalars(select(OperationLog)).all()
        assert len(logs) == 2
        assert all(log.operation == "bulk.offer.replace" for log in logs)
    finally:
        app.dependency_overrides.pop(get_keitaro_client, None)
