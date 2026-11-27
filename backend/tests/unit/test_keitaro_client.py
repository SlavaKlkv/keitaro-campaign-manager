"""Unit-тесты клиента Keitaro Admin API с использованием httpx.MockTransport."""

import json

import httpx
import pytest

from app.config import Settings
from app.keitaro import KeitaroClient, KeitaroError


def _make_settings(base_url: str = "https://keitaro.example.com/admin") -> Settings:
    return Settings(
        keitaro_base_url=base_url,
        keitaro_api_key="secret-test-key",
        keitaro_timeout_seconds=5.0,
        _env_file=None,
    )


async def test_client_sends_api_key_and_hits_all_endpoints() -> None:
    """Проверяет маршруты, методы, параметры и заголовок Api-Key для всех операций клиента."""
    recorded: list[tuple[str, str, str | None, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        recorded.append(
            (
                request.method,
                request.url.path + (f"?{request.url.query.decode()}" if request.url.query else ""),
                request.headers.get("Api-Key"),
                body,
            )
        )
        return httpx.Response(200, json={"ok": True, "path": request.url.path})

    async with KeitaroClient(_make_settings(), transport=httpx.MockTransport(handler)) as client:
        await client.list_campaigns(limit=20, offset=10)
        await client.get_campaign(5)
        await client.create_campaign({"name": "Camp"})
        await client.update_campaign(5, {"name": "Camp 2"})
        await client.enable_campaign(5)
        await client.disable_campaign(5)
        await client.delete_campaign(5)
        await client.list_campaign_streams(5)
        await client.create_stream({"campaign_id": 5})
        await client.get_stream(12)
        await client.update_stream(12, {"offers": []})
        await client.enable_stream(12)
        await client.disable_stream(12)
        await client.delete_stream(12)
        await client.list_offers()
        await client.get_offer(18001)
        await client.list_groups("campaigns")
        await client.list_domains()
        await client.list_traffic_sources()
        await client.build_report({"range": {"interval": "7 days"}})

    assert all(api_key == "secret-test-key" for _, _, api_key, _ in recorded)
    assert [(m, p) for m, p, _, _ in recorded] == [
        ("GET", "/admin_api/v1/campaigns?limit=20&offset=10"),
        ("GET", "/admin_api/v1/campaigns/5"),
        ("POST", "/admin_api/v1/campaigns"),
        ("PUT", "/admin_api/v1/campaigns/5"),
        ("POST", "/admin_api/v1/campaigns/5/enable"),
        ("POST", "/admin_api/v1/campaigns/5/disable"),
        ("DELETE", "/admin_api/v1/campaigns/5"),
        ("GET", "/admin_api/v1/campaigns/5/streams"),
        ("POST", "/admin_api/v1/streams"),
        ("GET", "/admin_api/v1/streams/12"),
        ("PUT", "/admin_api/v1/streams/12"),
        ("POST", "/admin_api/v1/streams/12/enable"),
        ("POST", "/admin_api/v1/streams/12/disable"),
        ("DELETE", "/admin_api/v1/streams/12"),
        ("GET", "/admin_api/v1/offers"),
        ("GET", "/admin_api/v1/offers/18001"),
        ("GET", "/admin_api/v1/groups?type=campaigns"),
        ("GET", "/admin_api/v1/domains"),
        ("GET", "/admin_api/v1/traffic_sources"),
        ("POST", "/admin_api/v1/report/build"),
    ]


@pytest.mark.parametrize("status_code", [401, 403])
async def test_client_maps_auth_errors(status_code: int) -> None:
    """Коды 401/403 преобразуются в KeitaroError с 502 и upstream_status."""
    transport = httpx.MockTransport(lambda _: httpx.Response(status_code, json={"message": "Unauthorized"}))
    async with KeitaroClient(_make_settings(), transport=transport) as client:
        with pytest.raises(KeitaroError) as exc_info:
            await client.list_offers()
    assert exc_info.value.status_code == 502
    assert exc_info.value.upstream_status == status_code


async def test_client_extracts_upstream_error_message() -> None:
    """HTTP 422/500 из Keitaro сохраняет текст ошибки в исключении."""
    transport = httpx.MockTransport(
        lambda _: httpx.Response(422, json={"message": "Invalid offer_id"})
    )
    async with KeitaroClient(_make_settings(), transport=transport) as client:
        with pytest.raises(KeitaroError) as exc_info:
            await client.update_stream(10, {"offers": []})
    assert exc_info.value.status_code == 502
    assert exc_info.value.upstream_status == 422
    assert "Invalid offer_id" in exc_info.value.message


async def test_client_handles_timeout() -> None:
    """Таймаут запроса преобразуется в KeitaroError с кодом 504."""

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with KeitaroClient(_make_settings(), transport=httpx.MockTransport(timeout_handler)) as client:
        with pytest.raises(KeitaroError) as exc_info:
            await client.list_campaigns()
    assert exc_info.value.status_code == 504


async def test_client_handles_network_error() -> None:
    """Сетевой сбой преобразуется в KeitaroError с кодом 502."""

    def network_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with KeitaroClient(_make_settings(), transport=httpx.MockTransport(network_handler)) as client:
        with pytest.raises(KeitaroError) as exc_info:
            await client.list_domains()
    assert exc_info.value.status_code == 502


async def test_client_handles_invalid_json_and_empty_204() -> None:
    """Невалидный JSON вызывает KeitaroError, а пустой 204 возвращает None."""
    bad_transport = httpx.MockTransport(lambda _: httpx.Response(200, text="<html>oops</html>"))
    async with KeitaroClient(_make_settings(), transport=bad_transport) as client:
        with pytest.raises(KeitaroError):
            await client.list_groups()

    empty_transport = httpx.MockTransport(lambda _: httpx.Response(204))
    async with KeitaroClient(_make_settings(), transport=empty_transport) as client:
        assert await client.delete_campaign(1) is None
