"""Роутер операций с кампаниями и потоками Keitaro."""

import asyncio
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db, log_operation
from app.deps import get_keitaro_client
from app.keitaro import KeitaroClient, KeitaroError
from app.keitaro_helpers import build_keitaro_campaign_url, build_tracking_url, extract_rows
from app.schemas import (
    CampaignCreateRequest,
    CampaignCreateResponse,
    CampaignStreamsResponse,
    CampaignSummary,
    StreamFilterItem,
    StreamInfo,
    StreamOfferItem,
    UpdateStreamOffersRequest,
    UpdateStreamOffersResponse,
)

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


def _to_campaign_summary(row: dict[str, Any], base_url: str) -> CampaignSummary:
    cid = int(row["id"])
    return CampaignSummary(
        id=cid,
        name=str(row.get("name", f"Campaign #{cid}")),
        alias=row.get("alias"),
        state=row.get("state"),
        domain_id=int(row["domain_id"]) if row.get("domain_id") is not None else None,
        domain=row.get("domain"),
        group_id=int(row["group_id"]) if row.get("group_id") is not None else None,
        group=row.get("group"),
        traffic_source_id=(
            int(row["traffic_source_id"])
            if row.get("traffic_source_id") is not None
            else None
        ),
        type=row.get("type"),
        cost_type=row.get("cost_type"),
        keitaro_url=build_keitaro_campaign_url(base_url, cid),
    )


@router.get("", response_model=list[CampaignSummary])
async def list_campaigns(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    client: KeitaroClient = Depends(get_keitaro_client),
) -> list[CampaignSummary]:
    """Возвращает список активных/архивных кампаний из Keitaro."""
    try:
        payload = await client.list_campaigns(limit=limit, offset=offset)
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    base_url = get_settings().keitaro_base_url
    return [
        _to_campaign_summary(row, base_url)
        for row in extract_rows(payload)
        if row.get("id") is not None and row.get("state") != "deleted"
    ]


@router.post("", response_model=CampaignCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreateRequest,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
) -> CampaignCreateResponse:
    """Создаёт кампанию (ротация по позиции, CPC) и 2 потока: Geo→Google и Offer 100%."""
    try:
        domains_raw, groups_raw, sources_raw, offers_raw = await asyncio.gather(
            client.list_domains(),
            client.list_groups("campaigns"),
            client.list_traffic_sources(),
            client.list_offers(),
        )
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    domain_rows = extract_rows(domains_raw)
    group_rows = extract_rows(groups_raw)
    source_rows = extract_rows(sources_raw)
    offer_rows = extract_rows(offers_raw)

    domain_row = next((r for r in domain_rows if str(r.get("id")) == str(payload.domain_id)), None)
    if domain_row is None:
        raise HTTPException(status_code=422, detail="Выбранный домен не найден в Keitaro")
    if not any(str(r.get("id")) == str(payload.group_id) for r in group_rows):
        raise HTTPException(status_code=422, detail="Выбранная группа кампаний не найдена в Keitaro")
    if not any(str(r.get("id")) == str(payload.traffic_source_id) for r in source_rows):
        raise HTTPException(status_code=422, detail="Выбранный источник трафика не найден в Keitaro")
    if not any(str(r.get("id")) == str(payload.offer_id) for r in offer_rows):
        raise HTTPException(status_code=422, detail="Выбранный оффер не найден в Keitaro")

    alias = payload.alias or f"cmp-{secrets.token_hex(4)}"
    campaign_id: int | None = None
    try:
        created: dict[str, Any] = await client.create_campaign(
            {
                "name": payload.name,
                "alias": alias,
                "type": "position",
                "cost_type": "CPC",
                "domain_id": payload.domain_id,
                "group_id": payload.group_id,
                "traffic_source_id": payload.traffic_source_id,
                "state": "active",
            }
        )
        campaign_id = int(created["id"])

        # Flow 1: перехват указанного гео и редирект на Google
        await client.create_stream(
            {
                "campaign_id": campaign_id,
                "name": f"Geo {payload.country_code}",
                "type": "regular",
                "position": 1,
                "schema": "redirect",
                "action_type": "http",
                "action_payload": "https://google.com",
                "state": "active",
                "filters": [
                    {
                        "name": "country",
                        "mode": "accept",
                        "payload": [payload.country_code],
                    }
                ],
            }
        )

        # Flow 2: выбранный оффер со 100% веса
        await client.create_stream(
            {
                "campaign_id": campaign_id,
                "name": "Офферы",
                "type": "default",
                "position": 2,
                "schema": "landings",
                "action_type": "do_nothing",
                "state": "active",
                "offers": [
                    {
                        "offer_id": payload.offer_id,
                        "share": 100,
                        "state": "active",
                    }
                ],
            }
        )
    except HTTPException:
        raise
    except (KeitaroError, KeyError, TypeError, ValueError) as exc:
        if campaign_id is not None:
            try:
                await client.disable_campaign(campaign_id)
            except KeitaroError:
                pass
        detail = (
            exc.message
            if isinstance(exc, KeitaroError)
            else "Неожиданный формат ответа Keitaro при создании кампании"
        )
        log_operation(
            db,
            operation="campaign.create",
            resource_type="campaign",
            resource_id=campaign_id,
            summary=f"Ошибка создания кампании '{payload.name}': {detail}",
            status="error",
            details={"country_code": payload.country_code, "offer_id": payload.offer_id},
        )
        status_code = exc.status_code if isinstance(exc, KeitaroError) else 502
        raise HTTPException(status_code=status_code, detail=detail) from exc

    resolved_alias = str(created.get("alias") or alias)
    log_operation(
        db,
        operation="campaign.create",
        resource_type="campaign",
        resource_id=campaign_id,
        summary=f"Создана кампания '{payload.name}' (Geo {payload.country_code}, оффер #{payload.offer_id})",
        status="success",
        details={
            "alias": resolved_alias,
            "country_code": payload.country_code,
            "offer_id": payload.offer_id,
            "domain_id": payload.domain_id,
            "group_id": payload.group_id,
            "traffic_source_id": payload.traffic_source_id,
        },
    )

    base_url = get_settings().keitaro_base_url
    return CampaignCreateResponse(
        id=campaign_id,
        name=str(created.get("name") or payload.name),
        alias=resolved_alias,
        country_code=payload.country_code,
        offer_id=payload.offer_id,
        domain_id=payload.domain_id,
        group_id=payload.group_id,
        traffic_source_id=payload.traffic_source_id,
        streams_created=2,
        tracking_url=build_tracking_url(domain_row.get("name"), resolved_alias),
        keitaro_url=build_keitaro_campaign_url(base_url, campaign_id),
    )


@router.get("/{campaign_id}/streams", response_model=CampaignStreamsResponse)
async def get_campaign_streams(
    campaign_id: int,
    client: KeitaroClient = Depends(get_keitaro_client),
) -> CampaignStreamsResponse:
    """Загружает карточку кампании и её потоки из Keitaro (FETCH STREAMS FROM KT)."""
    try:
        campaign_raw, streams_raw, offers_raw = await asyncio.gather(
            client.get_campaign(campaign_id),
            client.list_campaign_streams(campaign_id),
            client.list_offers(),
        )
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    if not isinstance(campaign_raw, dict) or campaign_raw.get("id") is None:
        raise HTTPException(status_code=404, detail="Кампания не найдена в Keitaro")

    offer_catalog: dict[int, dict[str, Any]] = {
        int(row["id"]): row
        for row in extract_rows(offers_raw)
        if row.get("id") is not None
    }

    streams: list[StreamInfo] = []
    for row in extract_rows(streams_raw):
        if row.get("id") is None:
            continue

        raw_filters = row.get("filters") if isinstance(row.get("filters"), list) else []
        filters = [
            StreamFilterItem(
                name=str(f.get("name", "")),
                mode=f.get("mode"),
                payload=f.get("payload"),
            )
            for f in raw_filters
            if isinstance(f, dict)
        ]

        raw_offers = row.get("offers") if isinstance(row.get("offers"), list) else []
        offers: list[StreamOfferItem] = []
        for item in raw_offers:
            if not isinstance(item, dict) or item.get("offer_id") is None:
                continue
            oid = int(item["offer_id"])
            catalog_entry = offer_catalog.get(oid, {})
            offers.append(
                StreamOfferItem(
                    offer_id=oid,
                    name=str(catalog_entry.get("name") or item.get("name") or f"Offer #{oid}"),
                    share=int(item.get("share") or 0),
                    state=str(item.get("state") or "active"),
                    country=(
                        catalog_entry.get("country")
                        if isinstance(catalog_entry.get("country"), list)
                        else []
                    ),
                )
            )

        streams.append(
            StreamInfo(
                id=int(row["id"]),
                campaign_id=int(row.get("campaign_id") or campaign_id),
                name=str(row.get("name") or f"Stream #{row['id']}"),
                type=row.get("type"),
                position=int(row["position"]) if row.get("position") is not None else None,
                weight=int(row["weight"]) if row.get("weight") is not None else None,
                schema=row.get("schema"),
                action_type=row.get("action_type"),
                action_payload=row.get("action_payload"),
                state=row.get("state"),
                filters=filters,
                offers=offers,
            )
        )

    streams.sort(key=lambda s: (s.position if s.position is not None else 9999, s.id))
    base_url = get_settings().keitaro_base_url
    return CampaignStreamsResponse(
        campaign=_to_campaign_summary(campaign_raw, base_url),
        streams=streams,
    )


@router.put(
    "/{campaign_id}/streams/{stream_id}/offers",
    response_model=UpdateStreamOffersResponse,
)
async def update_stream_offers(
    campaign_id: int,
    stream_id: int,
    payload: UpdateStreamOffersRequest,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
) -> UpdateStreamOffersResponse:
    """Обновляет список офферов и долей потока в Keitaro (PUSH TO KT)."""
    try:
        streams_raw, offers_raw = await asyncio.gather(
            client.list_campaign_streams(campaign_id),
            client.list_offers(),
        )
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    stream = next(
        (row for row in extract_rows(streams_raw) if int(row.get("id", -1)) == stream_id),
        None,
    )
    if stream is None:
        raise HTTPException(status_code=404, detail="Поток не найден в указанной кампании")
    if stream.get("schema") != "landings":
        raise HTTPException(
            status_code=409,
            detail="Редактирование офферов поддерживается только для потоков со схемой landings",
        )

    available_ids = {
        int(row["id"])
        for row in extract_rows(offers_raw)
        if row.get("id") is not None
    }
    unknown_ids = [item.offer_id for item in payload.offers if item.offer_id not in available_ids]
    if unknown_ids:
        raise HTTPException(
            status_code=422,
            detail=f"Неизвестные offer_id: {unknown_ids}",
        )

    keitaro_offers = [
        {"offer_id": item.offer_id, "share": item.share, "state": item.state}
        for item in payload.offers
    ]
    try:
        updated = await client.update_stream(stream_id, {"offers": keitaro_offers})
    except KeitaroError as exc:
        log_operation(
            db,
            operation="stream.offers.update",
            resource_type="stream",
            resource_id=stream_id,
            summary=f"Ошибка обновления офферов потока #{stream_id} (кампания #{campaign_id}): {exc.message}",
            status="error",
            details={"campaign_id": campaign_id, "offers": keitaro_offers},
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    log_operation(
        db,
        operation="stream.offers.update",
        resource_type="stream",
        resource_id=stream_id,
        summary=f"Обновлены офферы потока #{stream_id} кампании #{campaign_id} ({len(keitaro_offers)} шт.)",
        status="success",
        details={"campaign_id": campaign_id, "offers": keitaro_offers},
    )
    return UpdateStreamOffersResponse(
        campaign_id=campaign_id,
        stream_id=stream_id,
        offers=payload.offers,
        updated=isinstance(updated, dict) or updated is None,
    )


@router.delete("/{campaign_id}", status_code=status.HTTP_200_OK)
async def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
) -> dict[str, Any]:
    """Удаляет кампанию в Keitaro и фиксирует событие в журнале."""
    try:
        await client.delete_campaign(campaign_id)
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    log_operation(
        db,
        operation="campaign.delete",
        resource_type="campaign",
        resource_id=campaign_id,
        summary=f"Удалена кампания #{campaign_id}",
        status="success",
    )
    return {"deleted": True, "campaign_id": campaign_id}
