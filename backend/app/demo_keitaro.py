"""Встроенный in-memory mock-клиент Keitaro для запуска без реального API-ключа (DEMO_MODE=true)."""

from copy import deepcopy
from typing import Any

from app.keitaro import KeitaroError


class DemoKeitaroClient:
    """Полная in-memory имитация Keitaro Admin API v1 для демонстрации и тестов."""

    def __init__(self) -> None:
        self.base_url = "https://demo.keitaro.local"
        self._next_campaign_id = 104
        self._next_stream_id = 1007

        self._domains: list[dict[str, Any]] = [
            {"id": 10, "name": "https://demo-trk.example.com", "status": "active", "is_ssl": True, "state": "active"},
            {"id": 11, "name": "https://alt-trk.example.com", "status": "active", "is_ssl": True, "state": "active"},
        ]
        self._groups: list[dict[str, Any]] = [
            {"id": 20, "name": "Default", "type": "campaigns"},
            {"id": 21, "name": "FORTESTS", "type": "campaigns"},
            {"id": 22, "name": "Nutra EU", "type": "campaigns"},
        ]
        self._traffic_sources: list[dict[str, Any]] = [
            {"id": 30, "name": "Facebook Ads", "template_name": "facebook", "state": "active"},
            {"id": 31, "name": "FORTESTS", "template_name": "custom", "state": "active"},
            {"id": 32, "name": "TikTok Ads", "template_name": "tiktok", "state": "active"},
        ]
        self._offers: list[dict[str, Any]] = [
            {"id": 18001, "name": "18001 Oxys Cream RO", "group_id": 1, "group": "Nutra", "state": "active", "country": ["RO"]},
            {"id": 18002, "name": "18002 Miaflow RO", "group_id": 1, "group": "Nutra", "state": "active", "country": ["RO"]},
            {"id": 18003, "name": "18003 FitoMishki CL", "group_id": 1, "group": "Nutra", "state": "active", "country": ["CL"]},
            {"id": 18004, "name": "18004 GlucoPRO DE", "group_id": 1, "group": "Nutra", "state": "active", "country": ["DE"]},
            {"id": 18005, "name": "18005 CardioMax ES", "group_id": 1, "group": "Nutra", "state": "active", "country": ["ES"]},
            {"id": 18006, "name": "18006 SlimDrop AU", "group_id": 2, "group": "Beauty", "state": "active", "country": ["AU"]},
            {"id": 18007, "name": "18007 Legacy Archived Offer", "group_id": 2, "group": "Beauty", "state": "archived", "country": ["PL"]},
        ]

        self._campaigns: dict[int, dict[str, Any]] = {
            101: {
                "id": 101,
                "name": "demo_RO_nutra_split",
                "alias": "demo-ro-split",
                "state": "active",
                "domain_id": 10,
                "domain": "https://demo-trk.example.com",
                "group_id": 21,
                "group": "FORTESTS",
                "traffic_source_id": 31,
                "type": "position",
                "cost_type": "CPC",
            },
            102: {
                "id": 102,
                "name": "demo_DE_gluco_main",
                "alias": "demo-de-gluco",
                "state": "active",
                "domain_id": 10,
                "domain": "https://demo-trk.example.com",
                "group_id": 22,
                "group": "Nutra EU",
                "traffic_source_id": 30,
                "type": "position",
                "cost_type": "CPC",
            },
            103: {
                "id": 103,
                "name": "demo_ES_cardio_test",
                "alias": "demo-es-cardio",
                "state": "active",
                "domain_id": 11,
                "domain": "https://alt-trk.example.com",
                "group_id": 21,
                "group": "FORTESTS",
                "traffic_source_id": 32,
                "type": "position",
                "cost_type": "CPC",
            },
        }

        self._streams: dict[int, dict[str, Any]] = {
            1001: {
                "id": 1001,
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
            1002: {
                "id": 1002,
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
            1003: {
                "id": 1003,
                "campaign_id": 102,
                "name": "Geo DE",
                "type": "regular",
                "position": 1,
                "schema": "redirect",
                "action_type": "http",
                "action_payload": "https://google.com",
                "state": "active",
                "filters": [{"name": "country", "mode": "accept", "payload": ["DE"]}],
                "offers": [],
            },
            1004: {
                "id": 1004,
                "campaign_id": 102,
                "name": "Офферы",
                "type": "default",
                "position": 2,
                "schema": "landings",
                "action_type": "do_nothing",
                "state": "active",
                "filters": [],
                "offers": [
                    {"offer_id": 18004, "share": 70, "state": "active"},
                    {"offer_id": 18001, "share": 30, "state": "active"},
                ],
            },
            1005: {
                "id": 1005,
                "campaign_id": 103,
                "name": "Geo ES",
                "type": "regular",
                "position": 1,
                "schema": "redirect",
                "action_type": "http",
                "action_payload": "https://google.com",
                "state": "active",
                "filters": [{"name": "country", "mode": "accept", "payload": ["ES"]}],
                "offers": [],
            },
            1006: {
                "id": 1006,
                "campaign_id": 103,
                "name": "Офферы",
                "type": "default",
                "position": 2,
                "schema": "landings",
                "action_type": "do_nothing",
                "state": "active",
                "filters": [],
                "offers": [
                    {"offer_id": 18005, "share": 100, "state": "active"},
                ],
            },
        }

        self._offer_metrics: dict[int, dict[str, float | int]] = {
            18001: {"clicks": 420, "conversions": 26, "revenue": 520.0},
            18002: {"clicks": 380, "conversions": 15, "revenue": 285.0},
            18003: {"clicks": 190, "conversions": 7, "revenue": 112.0},
            18004: {"clicks": 510, "conversions": 34, "revenue": 748.0},
            18005: {"clicks": 260, "conversions": 12, "revenue": 216.0},
            18006: {"clicks": 15, "conversions": 1, "revenue": 18.0},
            18007: {"clicks": 12, "conversions": 0, "revenue": 0.0},
        }

    async def __aenter__(self) -> "DemoKeitaroClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def close(self) -> None:
        return None

    # --- Campaigns ---

    async def list_campaigns(
        self,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = [deepcopy(c) for c in self._campaigns.values() if c.get("state") != "deleted"]
        rows.sort(key=lambda r: int(r["id"]))
        start = offset or 0
        end = start + limit if limit is not None else None
        return rows[start:end]

    async def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        cmp_row = self._campaigns.get(campaign_id)
        if cmp_row is None or cmp_row.get("state") == "deleted":
            raise KeitaroError(f"Кампания #{campaign_id} не найдена", status_code=502, upstream_status=404)
        return deepcopy(cmp_row)

    async def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        cid = self._next_campaign_id
        self._next_campaign_id += 1
        domain_row = next((d for d in self._domains if d["id"] == payload.get("domain_id")), None)
        group_row = next((g for g in self._groups if g["id"] == payload.get("group_id")), None)
        record = {
            "id": cid,
            **deepcopy(payload),
            "domain": domain_row["name"] if domain_row else None,
            "group": group_row["name"] if group_row else None,
        }
        self._campaigns[cid] = record
        return deepcopy(record)

    async def update_campaign(self, campaign_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        if campaign_id not in self._campaigns:
            raise KeitaroError(f"Кампания #{campaign_id} не найдена", status_code=502, upstream_status=404)
        self._campaigns[campaign_id].update(deepcopy(payload))
        return deepcopy(self._campaigns[campaign_id])

    async def delete_campaign(self, campaign_id: int) -> None:
        if campaign_id not in self._campaigns:
            raise KeitaroError(f"Кампания #{campaign_id} не найдена", status_code=502, upstream_status=404)
        self._campaigns[campaign_id]["state"] = "deleted"

    async def enable_campaign(self, campaign_id: int) -> dict[str, Any]:
        return await self.update_campaign(campaign_id, {"state": "active"})

    async def disable_campaign(self, campaign_id: int) -> dict[str, Any]:
        return await self.update_campaign(campaign_id, {"state": "disabled"})

    async def list_campaign_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        if campaign_id not in self._campaigns:
            raise KeitaroError(f"Кампания #{campaign_id} не найдена", status_code=502, upstream_status=404)
        rows = [
            deepcopy(s)
            for s in self._streams.values()
            if s.get("campaign_id") == campaign_id and s.get("state") != "deleted"
        ]
        rows.sort(key=lambda s: (s.get("position") or 9999, s["id"]))
        return rows

    # --- Streams ---

    async def create_stream(self, payload: dict[str, Any]) -> dict[str, Any]:
        sid = self._next_stream_id
        self._next_stream_id += 1
        record = {"id": sid, "offers": [], "filters": [], **deepcopy(payload)}
        self._streams[sid] = record
        return deepcopy(record)

    async def get_stream(self, stream_id: int) -> dict[str, Any]:
        stream = self._streams.get(stream_id)
        if stream is None:
            raise KeitaroError(f"Поток #{stream_id} не найден", status_code=502, upstream_status=404)
        return deepcopy(stream)

    async def update_stream(self, stream_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        stream = self._streams.get(stream_id)
        if stream is None:
            raise KeitaroError(f"Поток #{stream_id} не найден", status_code=502, upstream_status=404)
        stream.update(deepcopy(payload))
        return deepcopy(stream)

    async def delete_stream(self, stream_id: int) -> None:
        self._streams.pop(stream_id, None)

    async def enable_stream(self, stream_id: int) -> dict[str, Any]:
        return await self.update_stream(stream_id, {"state": "active"})

    async def disable_stream(self, stream_id: int) -> dict[str, Any]:
        return await self.update_stream(stream_id, {"state": "disabled"})

    # --- Offers ---

    async def list_offers(self) -> list[dict[str, Any]]:
        return deepcopy(self._offers)

    async def get_offer(self, offer_id: int) -> dict[str, Any]:
        offer = next((o for o in self._offers if o["id"] == offer_id), None)
        if offer is None:
            raise KeitaroError(f"Оффер #{offer_id} не найден", status_code=502, upstream_status=404)
        return deepcopy(offer)

    # --- Misc ---

    async def list_groups(self, group_type: str = "campaigns") -> list[dict[str, Any]]:
        return [deepcopy(g) for g in self._groups if g.get("type") == group_type]

    async def list_domains(self) -> list[dict[str, Any]]:
        return deepcopy(self._domains)

    async def list_traffic_sources(self) -> list[dict[str, Any]]:
        return deepcopy(self._traffic_sources)

    # --- Reports ---

    async def build_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Генерирует синтетический отчёт по офферам кампании для DEMO_MODE."""
        campaign_id: int | None = None
        for flt in payload.get("filters") or []:
            if isinstance(flt, dict) and flt.get("name") == "campaign_id" and flt.get("expression"):
                campaign_id = int(flt["expression"][0])
                break

        interval = (payload.get("range") or {}).get("interval", "7 days")
        factor = 0.25 if "today" in str(interval) else (3.0 if "30" in str(interval) else 1.0)

        offer_ids: set[int] = set()
        if campaign_id is not None and campaign_id in self._campaigns:
            for s in self._streams.values():
                if s.get("campaign_id") == campaign_id:
                    for item in s.get("offers") or []:
                        if item.get("offer_id") is not None:
                            offer_ids.add(int(item["offer_id"]))
        else:
            offer_ids = {int(o["id"]) for o in self._offers}

        rows: list[dict[str, Any]] = []
        for oid in sorted(offer_ids):
            base = self._offer_metrics.get(oid, {"clicks": 80, "conversions": 3, "revenue": 45.0})
            clicks = max(1, int(round(float(base["clicks"]) * factor)))
            conversions = int(round(float(base["conversions"]) * factor))
            revenue = round(float(base["revenue"]) * factor, 2)
            cr = round((conversions / clicks) * 100, 2) if clicks else 0.0
            epc = round(revenue / clicks, 4) if clicks else 0.0
            offer_meta = next((o for o in self._offers if o["id"] == oid), {})
            rows.append(
                {
                    "offer_id": oid,
                    "offer": offer_meta.get("name", f"Offer #{oid}"),
                    "clicks": clicks,
                    "conversions": conversions,
                    "cr": cr,
                    "epc": epc,
                    "revenue": revenue,
                }
            )
        return {"rows": rows, "total": len(rows)}


_demo_client = DemoKeitaroClient()


def get_demo_keitaro_client() -> DemoKeitaroClient:
    """Возвращает синглтон DemoKeitaroClient, сохраняющий состояние между запросами."""
    return _demo_client


def reset_demo_keitaro_client() -> DemoKeitaroClient:
    """Сбрасывает состояние DemoKeitaroClient к начальным фикстурам (для тестов)."""
    global _demo_client
    _demo_client = DemoKeitaroClient()
    return _demo_client
