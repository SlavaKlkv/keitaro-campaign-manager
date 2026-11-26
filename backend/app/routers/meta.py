"""Эндпоинт получения справочников Keitaro (домены, группы, источники, офферы)."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.deps import get_keitaro_client
from app.keitaro import KeitaroClient, KeitaroError
from app.keitaro_helpers import extract_rows, pick_default_id
from app.schemas import DomainItem, GroupItem, MetaResponse, OfferItem, TrafficSourceItem

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta", response_model=MetaResponse)
async def get_meta(client: KeitaroClient = Depends(get_keitaro_client)) -> MetaResponse:
    """Параллельно загружает домены, группы кампаний, источники трафика и офферы из Keitaro."""
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

    settings = get_settings()
    return MetaResponse(
        domains=domains,
        groups=groups,
        traffic_sources=traffic_sources,
        offers=offers,
        keitaro_base_url=settings.keitaro_base_url,
        defaults={
            "domain_id": pick_default_id(domain_rows),
            "group_id": pick_default_id(group_rows, ("FORTESTS", "adrobot")),
            "traffic_source_id": pick_default_id(source_rows, ("FORTESTS",)),
        },
    )
