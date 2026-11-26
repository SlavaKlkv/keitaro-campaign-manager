"""Unit-тесты асинхронного клиента Keitaro Admin API с httpx.MockTransport."""

import json

import httpx
import pytest

from app.keitaro import KeitaroClient, KeitaroError


@pytest.mark.asyncio
async def test_client_sends_api_key_and_covers_all_endpoints() -> None:
    """Проверяет пути, HTTP-методы, параметры и заголовок Api-Key для всех методов клиента."""
    recorded: list[tuple[str, str, dict | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        recorded.append((request.method, str(request.url), body, request.headers.get("Api-Key")))
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"ok": True, "path": request.url.path})

    transport = httpx.MockTransport(handler)
    async with KeitaroClient(
        "https://keitaro.example.com",
        "secret-key-123",
        transport=transport,
    ) as client:
        await client.list_campaigns(limit=50, offset=10)
        await client.get_campaign(7)
        await client.create_campaign({"name": "Test"})
        await client.update_campaign(7, {"name": "Updated"})
        await client.enable_campaign(7)
        await client.disable_campaign(7)
        await client.list_campaign_streams(7)
        await client.delete_campaign(7)

        await client.create_stream({"campaign_id": 7, "name": "Geo"})
        await client.get_stream(99)
        await client.update_stream(99, {"offers": [{"offer_id": 1, "share": 100}]})
        await client.enable_stream(99)
        await client.disable_stream(99)
        await client.delete_stream(99)

        await client.list_offers()
        await client.get_offer(18001)
        await client.list_groups("campaigns")
        await client.list_domains()
        await client.list_traffic_sources()

    assert len(recorded) == 19
    assert all(api_key == "secret-key-123" for _, _, _, api_key in recorded)
    assert recorded[0][0:2] == ("GET", "https://keitaro.example.com/admin_api/v1/campaigns?limit=50&offset=10")
    assert recorded[1][0:2] == ("GET", "https://keitaro.example.com/admin_api/v1/campaigns/7")
    assert recorded[2][0:3] == ("POST", "https://keitaro.example.com/admin_api/v1/campaigns", {"name": "Test"})
    assert recorded[3][0:3] == ("PUT", "https://keitaro.example.com/admin_api/v1/campaigns/7", {"name": "Updated"})
    assert recorded[7][0:2] == ("DELETE", "https://keitaro.example.com/admin_api/v1/campaigns/7")
    assert recorded[10][0:3] == (
        "PUT",
        "https://keitaro.example.com/admin_api/v1/streams/99",
        {"offers": [{"offer_id": 1, "share": 100}]},
    )
    assert recorded[16][0:2] == ("GET", "https://keitaro.example.com/admin_api/v1/groups?type=campaigns")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [(401, 502), (403, 502), (404, 404), (500, 502)],
)
async def test_client_maps_http_errors(status_code: int, expected_code: int) -> None:
    """Проверяет преобразование HTTP-ошибок Keitaro в KeitaroError."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"message": "boom"})

    async with KeitaroClient(
        "https://keitaro.example.com",
        "key",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(KeitaroError) as exc_info:
            await client.list_campaigns()
    assert exc_info.value.status_code == expected_code
    assert exc_info.value.upstream_status == status_code


@pytest.mark.asyncio
async def test_client_handles_timeout_and_invalid_json() -> None:
    """Проверяет обработку таймаута (504) и невалидного JSON (502)."""

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with KeitaroClient(
        "https://keitaro.example.com",
        "key",
        transport=httpx.MockTransport(timeout_handler),
    ) as client:
        with pytest.raises(KeitaroError) as exc_info:
            await client.list_offers()
    assert exc_info.value.status_code == 504

    def bad_json_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async with KeitaroClient(
        "https://keitaro.example.com",
        "key",
        transport=httpx.MockTransport(bad_json_handler),
    ) as client:
        with pytest.raises(KeitaroError) as exc_info:
            await client.list_domains()
    assert exc_info.value.status_code == 502
