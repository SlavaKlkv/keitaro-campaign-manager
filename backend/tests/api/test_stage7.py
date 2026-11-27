"""API- и unit-тесты для Этапа 7: статистика /stats и аудит здоровья кампаний."""

from collections.abc import AsyncGenerator
from typing import Any

from fastapi.testclient import TestClient

from app.deps import get_keitaro_client
from app.health_audit import audit_campaign_streams
from app.main import app


class FakeAnalyticsKeitaro:
    """Фейковый клиент Keitaro с отчётами и проблемными потоками для аудита."""

    def __init__(self) -> None:
        self.base_url = "https://keitaro.example.com"
        self.last_report_payload: dict[str, Any] | None = None

    async def list_campaigns(self, limit: int | None = None, offset: int | None = None) -> list[dict[str, Any]]:
        return [
            {"id": 101, "name": "Healthy Camp", "state": "active"},
            {"id": 102, "name": "Broken Camp", "state": "active"},
        ]

    async def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        return {"id": campaign_id, "name": f"Camp #{campaign_id}", "state": "active"}

    async def list_offers(self) -> list[dict[str, Any]]:
        return [
            {"id": 18001, "name": "Active Offer", "state": "active", "country": ["RO"]},
            {"id": 18002, "name": "Archived Offer", "state": "archived", "country": ["RO"]},
        ]

    async def list_campaign_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        if campaign_id == 101:
            return [
                {
                    "id": 1,
                    "campaign_id": 101,
                    "name": "Офферы",
                    "schema": "landings",
                    "state": "active",
                    "offers": [{"offer_id": 18001, "share": 100, "state": "active"}],
                }
            ]
        return [
            {
                "id": 2,
                "campaign_id": 102,
                "name": "Офферы",
                "schema": "landings",
                "state": "active",
                "offers": [
                    {"offer_id": 18001, "share": 40, "state": "active"},
                    {"offer_id": 18002, "share": 40, "state": "active"},
                ],
            }
        ]

    async def build_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_report_payload = payload
        return {
            "rows": [
                {
                    "offer_id": 18001,
                    "offer": "Active Offer",
                    "clicks": 200,
                    "conversions": 10,
                    "revenue": 150.0,
                }
            ]
        }


def test_audit_campaign_streams_detects_all_issue_types() -> None:
    """Аудит выявляет пустые потоки, архивные/удалённые офферы, дубли и сумму != 100%."""
    catalog = {
        1: {"id": 1, "state": "active"},
        2: {"id": 2, "state": "archived"},
    }

    empty_health = audit_campaign_streams(
        [{"id": 10, "name": "Empty", "schema": "landings", "state": "active", "offers": []}],
        catalog,
    )
    assert empty_health.status == "error"
    assert [i.code for i in empty_health.issues] == ["no_active_offers"]

    bad_health = audit_campaign_streams(
        [
            {
                "id": 11,
                "name": "Broken",
                "schema": "landings",
                "state": "active",
                "offers": [
                    {"offer_id": 1, "share": 30, "state": "active"},
                    {"offer_id": 1, "share": 30, "state": "active"},
                    {"offer_id": 2, "share": 20, "state": "active"},
                    {"offer_id": 999, "share": 10, "state": "active"},
                ],
            }
        ],
        catalog,
    )
    assert bad_health.status == "error"
    codes = {i.code for i in bad_health.issues}
    assert codes == {"archived_or_deleted_offer", "duplicate_offers", "invalid_share_sum"}


def test_campaign_stats_and_health_endpoints(api_client: TestClient) -> None:
    """GET /stats и GET /health возвращают нормализованную статистику и сводку здоровья."""
    fake = FakeAnalyticsKeitaro()

    async def _override() -> AsyncGenerator[FakeAnalyticsKeitaro, None]:
        yield fake

    app.dependency_overrides[get_keitaro_client] = _override
    try:
        stats_resp = api_client.get("/api/campaigns/101/stats?period=30d")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["period"] == "30d"
        assert fake.last_report_payload is not None
        assert fake.last_report_payload["range"]["interval"] == "30 days ago"
        assert len(stats["offers"]) == 1
        assert stats["offers"][0]["cr"] == 5.0
        assert stats["offers"][0]["epc"] == 0.75

        health_resp = api_client.get("/api/campaigns/health")
        assert health_resp.status_code == 200
        health_map = health_resp.json()
        assert health_map["101"]["status"] == "ok"
        assert health_map["102"]["status"] == "error"
        assert {i["code"] for i in health_map["102"]["issues"]} == {
            "archived_or_deleted_offer",
            "invalid_share_sum",
        }

        streams_resp = api_client.get("/api/campaigns/102/streams")
        assert streams_resp.status_code == 200
        assert streams_resp.json()["health"]["status"] == "error"
    finally:
        app.dependency_overrides.pop(get_keitaro_client, None)
