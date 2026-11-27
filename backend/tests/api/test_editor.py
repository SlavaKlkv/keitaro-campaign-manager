"""API-тесты редактора кампаний: загрузка потоков и PUSH TO KT."""

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


class FakeEditorKeitaroClient:
    """Поддельный клиент Keitaro для тестирования сценариев редактора."""

    def __init__(self, *, fail_update: bool = False) -> None:
        self.base_url = "https://keitaro.example.com"
        self.fail_update = fail_update
        self.updated_streams: list[tuple[int, dict[str, Any]]] = []

    async def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        if campaign_id == 999:
            raise KeitaroError("Campaign not found", status_code=502, upstream_status=404)
        return {
            "id": campaign_id,
            "name": "Campaign 2",
            "alias": "cmp-2",
            "state": "active",
            "domain_id": 10,
            "group_id": 21,
            "traffic_source_id": 31,
            "type": "position",
            "cost_type": "CPC",
        }

    async def list_campaign_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        return [
            {
                "id": 502,
                "campaign_id": campaign_id,
                "name": "Офферы",
                "type": "default",
                "position": 2,
                "schema": "landings",
                "action_type": "do_nothing",
                "state": "active",
                "filters": [],
                "offers": [
                    {"offer_id": 18001, "share": 50, "state": "active"},
                    {"offer_id": 18002, "share": 50, "state": "active"},
                ],
            },
            {
                "id": 501,
                "campaign_id": campaign_id,
                "name": "Geo AU",
                "type": "regular",
                "position": 1,
                "schema": "redirect",
                "action_type": "http",
                "action_payload": "https://google.com",
                "state": "active",
                "filters": [{"name": "country", "mode": "accept", "payload": ["AU"]}],
                "offers": [],
            },
        ]

    async def list_offers(self) -> list[dict[str, Any]]:
        return [
            {"id": 18001, "name": "11112 Oxys", "country": ["RO"]},
            {"id": 18002, "name": "Miaflow", "country": ["RO"]},
            {"id": 18003, "name": "FitoMishki", "country": ["CL"]},
        ]

    async def update_stream(self, stream_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if self.fail_update:
            raise KeitaroError("Upstream update failed", status_code=502)
        self.updated_streams.append((stream_id, payload))
        return {"id": stream_id, **payload}


@pytest.fixture()
def fake_editor_kt() -> FakeEditorKeitaroClient:
    return FakeEditorKeitaroClient()


@pytest.fixture()
def editor_client(
    api_client: TestClient,
    fake_editor_kt: FakeEditorKeitaroClient,
) -> Iterator[TestClient]:
    async def _override() -> AsyncGenerator[FakeEditorKeitaroClient]:
        yield fake_editor_kt

    app.dependency_overrides[get_keitaro_client] = _override
    yield api_client
    app.dependency_overrides.pop(get_keitaro_client, None)


def test_get_campaign_streams_enriches_offers_and_sorts_by_position(
    editor_client: TestClient,
) -> None:
    """GET /api/campaigns/{id}/streams сортирует потоки и подставляет названия офферов."""
    resp = editor_client.get("/api/campaigns/55/streams")
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaign"]["id"] == 55
    assert data["campaign"]["keitaro_url"] == "https://keitaro.example.com/admin/#!/campaigns/55"
    streams = data["streams"]
    assert [s["id"] for s in streams] == [501, 502]
    assert streams[0]["schema"] == "redirect"
    assert [o["name"] for o in streams[1]["offers"]] == ["11112 Oxys", "Miaflow"]


def test_update_stream_offers_pushes_to_keitaro_and_logs(
    editor_client: TestClient,
    fake_editor_kt: FakeEditorKeitaroClient,
    db_session: Session,
) -> None:
    """PUT /api/campaigns/{id}/streams/{stream_id}/offers обновляет поток и пишет лог."""
    resp = editor_client.put(
        "/api/campaigns/55/streams/502/offers",
        json={
            "offers": [
                {"offer_id": 18001, "share": 38, "state": "active"},
                {"offer_id": 18002, "share": 37, "state": "active"},
                {"offer_id": 18003, "share": 25, "state": "active"},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] is True
    assert len(fake_editor_kt.updated_streams) == 1
    sid, sent_payload = fake_editor_kt.updated_streams[0]
    assert sid == 502
    assert len(sent_payload["offers"]) == 3

    logs = db_session.scalars(select(OperationLog)).all()
    assert len(logs) == 1
    assert logs[0].operation == "stream.offers.update"
    assert logs[0].status == "success"
    assert logs[0].resource_id == 502


def test_update_stream_offers_validates_sum_100_and_schema(
    editor_client: TestClient,
) -> None:
    """Сумма долей != 100% возвращает 422, а redirect-поток возвращает 409."""
    bad_sum = editor_client.put(
        "/api/campaigns/55/streams/502/offers",
        json={"offers": [{"offer_id": 18001, "share": 60, "state": "active"}]},
    )
    assert bad_sum.status_code == 422

    wrong_schema = editor_client.put(
        "/api/campaigns/55/streams/501/offers",
        json={"offers": [{"offer_id": 18001, "share": 100, "state": "active"}]},
    )
    assert wrong_schema.status_code == 409


def test_update_stream_offers_logs_error_when_keitaro_fails(
    api_client: TestClient,
    db_session: Session,
) -> None:
    """При ошибке Keitaro API возвращается 502 и фиксируется error-запись в журнале."""
    broken = FakeEditorKeitaroClient(fail_update=True)

    async def _override() -> AsyncGenerator[FakeEditorKeitaroClient]:
        yield broken

    app.dependency_overrides[get_keitaro_client] = _override
    try:
        resp = api_client.put(
            "/api/campaigns/55/streams/502/offers",
            json={"offers": [{"offer_id": 18001, "share": 100, "state": "active"}]},
        )
    finally:
        app.dependency_overrides.pop(get_keitaro_client, None)

    assert resp.status_code == 502
    logs = db_session.scalars(select(OperationLog)).all()
    assert len(logs) == 1
    assert logs[0].status == "error"
