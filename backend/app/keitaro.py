"""Асинхронный HTTP-клиент для работы с Keitaro Admin API v1."""

from typing import Any

import httpx

from app.config import Settings


class KeitaroError(Exception):
    """Ошибка взаимодействия с Keitaro Admin API."""

    def __init__(
        self,
        message: str,
        status_code: int = 502,
        upstream_status: int | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.upstream_status = upstream_status
        super().__init__(message)


def _extract_error_detail(response: httpx.Response) -> str:
    """Извлекает диагностическое сообщение из ответа Keitaro при HTTP-ошибке."""
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:300] if text else f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        for key in ("message", "error", "detail"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        if isinstance(payload.get("errors"), (list, dict)):
            return str(payload["errors"])[:300]
    return f"HTTP {response.status_code}"


class KeitaroClient:
    """Обёртка над httpx.AsyncClient с авторизацией по заголовку Api-Key."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        base_url = settings.keitaro_base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{base_url}/admin_api/v1/",
            headers={"Api-Key": settings.keitaro_api_key.get_secret_value()},
            timeout=settings.keitaro_timeout_seconds,
            transport=transport,
        )

    async def __aenter__(self) -> KeitaroClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Закрывает внутренний пул соединений httpx."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method,
                path.lstrip("/"),
                params=params,
                json=json_body,
            )
        except httpx.TimeoutException as exc:
            raise KeitaroError("Превышено время ожидания ответа от Keitaro API", status_code=504) from exc
        except httpx.RequestError as exc:
            raise KeitaroError("Не удалось подключиться к серверу Keitaro API", status_code=502) from exc

        if response.status_code in (401, 403):
            raise KeitaroError(
                "Keitaro API отклонил ключ авторизации",
                status_code=502,
                upstream_status=response.status_code,
            )

        if response.is_error:
            detail = _extract_error_detail(response)
            raise KeitaroError(
                f"Keitaro API вернул ошибку ({response.status_code}): {detail}",
                status_code=502,
                upstream_status=response.status_code,
            )

        if response.status_code == 204 or not response.content.strip():
            return None

        try:
            return response.json()
        except ValueError as exc:
            raise KeitaroError("Keitaro API вернул некорректный JSON", status_code=502) from exc

    # --- Campaigns ---

    async def list_campaigns(
        self,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Any:
        """Возвращает список кампаний (опционально с limit/offset)."""
        params: dict[str, str | int] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        return await self._request("GET", "campaigns", params=params or None)

    async def get_campaign(self, campaign_id: int) -> Any:
        """Возвращает детальную информацию о кампании по ID."""
        return await self._request("GET", f"campaigns/{campaign_id}")

    async def create_campaign(self, payload: dict[str, Any]) -> Any:
        """Создаёт кампанию в Keitaro."""
        return await self._request("POST", "campaigns", json_body=payload)

    async def update_campaign(self, campaign_id: int, payload: dict[str, Any]) -> Any:
        """Обновляет параметры существующей кампании."""
        return await self._request("PUT", f"campaigns/{campaign_id}", json_body=payload)

    async def delete_campaign(self, campaign_id: int) -> Any:
        """Удаляет кампанию по ID."""
        return await self._request("DELETE", f"campaigns/{campaign_id}")

    async def enable_campaign(self, campaign_id: int) -> Any:
        """Включает кампанию."""
        return await self._request("POST", f"campaigns/{campaign_id}/enable", json_body={})

    async def disable_campaign(self, campaign_id: int) -> Any:
        """Выключает кампанию."""
        return await self._request("POST", f"campaigns/{campaign_id}/disable", json_body={})

    async def list_campaign_streams(self, campaign_id: int) -> Any:
        """Возвращает потоки указанной кампании."""
        return await self._request("GET", f"campaigns/{campaign_id}/streams")

    # --- Streams ---

    async def create_stream(self, payload: dict[str, Any]) -> Any:
        """Создаёт поток в кампании."""
        return await self._request("POST", "streams", json_body=payload)

    async def get_stream(self, stream_id: int) -> Any:
        """Возвращает поток по ID."""
        return await self._request("GET", f"streams/{stream_id}")

    async def update_stream(self, stream_id: int, payload: dict[str, Any]) -> Any:
        """Обновляет поток по ID (включая список офферов и их доли)."""
        return await self._request("PUT", f"streams/{stream_id}", json_body=payload)

    async def delete_stream(self, stream_id: int) -> Any:
        """Удаляет поток по ID."""
        return await self._request("DELETE", f"streams/{stream_id}")

    async def enable_stream(self, stream_id: int) -> Any:
        """Включает поток."""
        return await self._request("POST", f"streams/{stream_id}/enable", json_body={})

    async def disable_stream(self, stream_id: int) -> Any:
        """Выключает поток."""
        return await self._request("POST", f"streams/{stream_id}/disable", json_body={})

    # --- Offers ---

    async def list_offers(self) -> Any:
        """Возвращает список офферов."""
        return await self._request("GET", "offers")

    async def get_offer(self, offer_id: int) -> Any:
        """Возвращает информацию об оффере по ID."""
        return await self._request("GET", f"offers/{offer_id}")

    # --- Misc ---

    async def list_groups(self, group_type: str = "campaigns") -> Any:
        """Возвращает группы указанного типа (по умолчанию campaigns)."""
        return await self._request("GET", "groups", params={"type": group_type})

    async def list_domains(self) -> Any:
        """Возвращает список припаркованных доменов."""
        return await self._request("GET", "domains")

    async def list_traffic_sources(self) -> Any:
        """Возвращает список источников трафика."""
        return await self._request("GET", "traffic_sources")

    # --- Reports ---

    async def build_report(self, payload: dict[str, Any]) -> Any:
        """Строит аналитический отчёт Keitaro (POST /report/build)."""
        return await self._request("POST", "report/build", json_body=payload)
