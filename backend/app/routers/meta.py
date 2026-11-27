"""Эндпоинт получения справочников Keitaro (домены, группы, источники, офферы) с TTL-кэшем."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.cache import meta_cache
from app.config import get_settings
from app.deps import get_keitaro_client
from app.keitaro import KeitaroClient, KeitaroError
from app.keitaro_helpers import extract_rows, pick_default_id
from app.schemas import DomainItem, GroupItem, MetaResponse, OfferItem, TrafficSourceItem

router = APIRouter(prefix="/api", tags=["meta"])


def _resolve_default_id(
    rows: list[dict[str, Any]],
    configured_id: int | None,
    preferred_names: tuple[str, ...] = (),
) -> int | None:
    """Выбирает сконфигурированный ID из .env (если есть в справочнике), иначе fallback на pick_default_id."""
    if configured_id is not None:
        if any(row.get("id") is not None and int(row["id"]) == configured_id for row in rows):
            return configured_id
    return pick_default_id(rows, preferred_names)


@router.get("/meta", response_model=MetaResponse)
async def get_meta(
    refresh: bool = Query(default=False, description="Принудительно сбросить кэш и обновить справочники из Keitaro"),
    client: KeitaroClient = Depends(get_keitaro_client),
) -> MetaResponse:
    """Параллельно загружает справочники из Keitaro с кэшированием по KEITARO_CACHE_TTL_SECONDS."""
    settings = get_settings()
    base_url = getattr(client, "base_url", None) or settings.keitaro_base_url
    cache_key = f"{'demo' if settings.demo_mode else 'live'}:{base_url}:{type(client).__name__}"

    if not refresh and settings.keitaro_cache_ttl_seconds > 0:
        cached = meta_cache.get(cache_key)
        if cached is not None:
            cached_payload, cached_at = cached
            return cached_payload.model_copy(update={"cached": True, "cached_at": cached_at})

    try:
        domains_raw, groups_raw, sources_raw, offers_raw = await asyncio.gather(
            client.list_domains(),
            client.list_groups("campaigns"),
            client.list_traffic_sources(),
            client.list_offers(),
        )
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    domain_rows = [r for r in extract_rows(domains_raw) if r.get("state") != "deleted"]
    group_rows = extract_rows(groups_raw)
    source_rows = [r for r in extract_rows(sources_raw) if r.get("state") != "deleted"]
    offer_rows = [r for r in extract_rows(offers_raw) if r.get("state") != "deleted"]

    domains = [
        DomainItem(
            id=int(r["id"]),
            name=str(r.get("name", f"Domain #{r['id']}")),
            status=r.get("status"),
            is_ssl=r.get("is_ssl"),
            state=r.get("state"),
        )
        for r in domain_rows
        if r.get("id") is not None
    ]
    groups = [
        GroupItem(
            id=int(r["id"]),
            name=str(r.get("name", f"Group #{r['id']}")),
            type=r.get("type"),
        )
        for r in group_rows
        if r.get("id") is not None
    ]
    traffic_sources = [
        TrafficSourceItem(
            id=int(r["id"]),
            name=str(r.get("name", f"Source #{r['id']}")),
            template_name=r.get("template_name"),
            state=r.get("state"),
        )
        for r in source_rows
        if r.get("id") is not None
    ]
    offers = [
        OfferItem(
            id=int(r["id"]),
            name=str(r.get("name", f"Offer #{r['id']}")),
            group_id=int(r["group_id"]) if r.get("group_id") is not None else None,
            group=r.get("group"),
            state=r.get("state"),
            country=r.get("country") if isinstance(r.get("country"), list) else [],
        )
        for r in offer_rows
        if r.get("id") is not None
    ]

    result = MetaResponse(
        domains=domains,
        groups=groups,
        traffic_sources=traffic_sources,
        offers=offers,
        keitaro_base_url=base_url,
        defaults={
            "domain_id": _resolve_default_id(domain_rows, settings.default_domain_id),
            "group_id": _resolve_default_id(group_rows, settings.default_group_id, ("FORTESTS", "adrobot")),
            "traffic_source_id": _resolve_default_id(source_rows, settings.default_traffic_source_id, ("FORTESTS",)),
        },
        campaign_name_prefix=settings.campaign_name_prefix,
        demo_mode=settings.demo_mode,
        cached=False,
        cached_at=None,
    )
    cached_at = meta_cache.set(cache_key, result, settings.keitaro_cache_ttl_seconds)
    if settings.keitaro_cache_ttl_seconds > 0:
        result = result.model_copy(update={"cached_at": cached_at})
    return result
