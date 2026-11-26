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


class KeitaroClient:
    """Обёртка над httpx.AsyncClient для методов Keitaro Admin API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        normalized_base = base_url.strip().rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{normalized_base}/admin_api/v1/",
            headers={"Api-Key": api_key},
            timeout=timeout_seconds,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "KeitaroClient":
        """Создаёт клиент из объекта настроек приложения."""
        return cls(
            base_url=settings.keitaro_base_url,
            api_key=settings.keitaro_api_key.get_secret_value(),
            timeout_seconds=settings.keitaro_timeout_seconds,
        )

    async def __aenter__(self) -> "KeitaroClient":
        return self

    async def __aexit__(self, *_: object) -> None:
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
            raise KeitaroError("Не удалось подключиться к Keitaro API", status_code=502) from exc

        if response.status_code in (401, 403):
            raise KeitaroError(
                "Keitaro API отклонил ключ доступа (401/403)",
                status_code=502,
                upstream_status=response.status_code,
            )

        if response.status_code == 404:
            raise KeitaroError(
                f"Ресурс Keitaro не найден: {path}",
                status_code=404,
                upstream_status=404,
            )

        if response.is_error:
            detail = self._extract_error_detail(response)
            raise KeitaroError(
                f"Ошибка Keitaro API (HTTP {response.status_code}): {detail}",
                status_code=502,
                upstream_status=response.status_code,
            )

        if response.status_code == 204 or not response.content:
            return {}

        try:
            return response.json()
        except ValueError as exc:
            raise KeitaroError("Keitaro API вернул некорректный JSON", status_code=502) from exc

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        """Извлекает читаемое сообщение об ошибке из ответа Keitaro."""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                for key in ("message", "error", "detail"):
                    value = payload.get(key)
                    if value:
                        return str(value)
                return str(payload)
        except ValueError:
            pass
        text = response.text.strip()
        return text[:200] if text else "пустой ответ"

    # --- Campaigns ---

    async def list_campaigns(self, limit: int = 100, offset: int = 0) -> Any:
        """Возвращает список кампаний Keitaro."""
        return await self._request("GET", "campaigns", params={"limit": limit, "offset": offset})

    async def get_campaign(self, campaign_id: int) -> Any:
        """Возвращает кампанию по её ID."""
        return await self._request("GET", f"campaigns/{campaign_id}")

    async def create_campaign(self, payload: dict[str, Any]) -> Any:
        """Создаёт кампанию в Keitaro (поддерживает вложенные потоки при необходимости)."""
        return await self._request("POST", "campaigns", json_body=payload)

    async def update_campaign(self, campaign_id: int, payload: dict[str, Any]) -> Any:
        """Обновляет параметры существующей кампании."""
        return await self._request("PUT", f"campaigns/{campaign_id}", json_body=payload)

    async def delete_campaign(self, campaign_id: int) -> Any:
        """Удаляет (перемещает в архив/корзину) кампанию по ID."""
        return await self._request("DELETE", f"campaigns/{campaign_id}")

    async def enable_campaign(self, campaign_id: int) -> Any:
        """Включает кампанию."""
        return await self._request("POST", f"campaigns/{campaign_id}/enable", json_body={})

    async def disable_campaign(self, campaign_id: int) -> Any:
        """Отключает кампанию."""
        return await self._request("POST", f"campaigns/{campaign_id}/disable", json_body={})

    async def list_campaign_streams(self, campaign_id: int) -> Any:
        """Возвращает потоки указанной кампании."""
        return await self._request("GET", f"campaigns/{campaign_id}/streams")

    # --- Streams ---

    async def create_stream(self, payload: dict[str, Any]) -> Any:
        """Создаёт новый поток в кампании."""
        return await self._request("POST", "streams", json_body=payload)

    async def get_stream(self, stream_id: int) -> Any:
        """Возвращает данные потока по его ID."""
        return await self._request("GET", f"streams/{stream_id}")

    async def update_stream(self, stream_id: int, payload: dict[str, Any]) -> Any:
        """Обновляет поток (включая список офферов и фильтры)."""
        return await self._request("PUT", f"streams/{stream_id}", json_body=payload)

    async def delete_stream(self, stream_id: int) -> Any:
        """Удаляет поток по ID."""
        return await self._request("DELETE", f"streams/{stream_id}")

    async def enable_stream(self, stream_id: int) -> Any:
        """Включает поток."""
        return await self._request("POST", f"streams/{stream_id}/enable", json_body={})

    async def disable_stream(self, stream_id: int) -> Any:
        """Отключает поток."""
        return await self._request("POST", f"streams/{stream_id}/disable", json_body={})

    # --- Offers ---

    async def list_offers(self) -> Any:
        """Возвращает список всех офферов Keitaro."""
        return await self._request("GET", "offers")

    async def get_offer(self, offer_id: int) -> Any:
        """Возвращает данные оффера по его ID."""
        return await self._request("GET", f"offers/{offer_id}")

    # --- Misc ---

    async def list_groups(self, group_type: str = "campaigns") -> Any:
        """Возвращает группы указанного типа (campaigns, offers, landings, domains)."""
        return await self._request("GET", "groups", params={"type": group_type})

    async def list_domains(self) -> Any:
        """Возвращает список доменов трекера."""
        return await self._request("GET", "domains")

    async def list_traffic_sources(self) -> Any:
        """Возвращает список источников трафика."""
        return await self._request("GET", "traffic_sources")
