"""Роутер массовых операций: Bulk Create, Clone to GEOs, Bulk Offer Replace."""

import asyncio
from copy import deepcopy
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db, log_operation
from app.deps import get_keitaro_client
from app.keitaro import KeitaroClient, KeitaroError
from app.keitaro_helpers import build_keitaro_campaign_url, build_tracking_url, extract_rows
from app.routers.campaigns import (
    apply_campaign_name_prefix,
    compute_offer_diff,
    upsert_stream_snapshots,
)
from app.schemas import (
    BulkCampaignCreateRequest,
    BulkCampaignCreateResponse,
    BulkCampaignResultItem,
    BulkOfferReplaceApplyResponse,
    BulkOfferReplaceApplyResult,
    BulkOfferReplacePreviewResponse,
    BulkOfferReplaceRequest,
    BulkReplaceStreamPreview,
    BulkReplaceStreamSkipped,
    CloneGeoResultItem,
    CloneGeosRequest,
    CloneGeosResponse,
)

router = APIRouter(prefix="/api/campaigns", tags=["bulk"])


def _redistribute_shares_to_100(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Пропорционально перераспределяет доли активных офферов до суммы ровно 100%."""
    if not offers:
        return []
    total = sum(int(o.get("share") or 0) for o in offers)
    result = [dict(o) for o in offers]
    if total <= 0:
        base = 100 // len(result)
        rem = 100 % len(result)
        for idx, item in enumerate(result):
            item["share"] = base + (1 if idx < rem else 0)
        return result

    allocated = 0
    remainders: list[tuple[int, float]] = []
    for idx, item in enumerate(result):
        exact = (100.0 * int(item.get("share") or 0)) / total
        floored = int(exact)
        item["share"] = floored
        allocated += floored
        remainders.append((idx, exact - floored))

    remainders.sort(key=lambda pair: pair[1], reverse=True)
    left = 100 - allocated
    for idx, _ in remainders[:left]:
        result[idx]["share"] += 1
    return result


def _compute_stream_replacement(
    raw_offers: list[dict[str, Any]],
    *,
    source_offer_id: int,
    target_offer_id: int | None,
    offer_catalog: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Строит before/after для потока при замене или отключении оффера. Возвращает (before, after, skip_reason)."""
    before: list[dict[str, Any]] = [
        {
            "offer_id": int(item["offer_id"]),
            "name": str(
                offer_catalog.get(int(item["offer_id"]), {}).get("name")
                or item.get("name")
                or f"Offer #{item['offer_id']}"
            ),
            "share": int(item.get("share") or 0),
            "state": str(item.get("state") or "active"),
        }
        for item in raw_offers
        if isinstance(item, dict) and item.get("offer_id") is not None
    ]

    active_before = [o for o in before if o["state"] == "active"]
    source_item = next((o for o in active_before if o["offer_id"] == source_offer_id), None)
    if source_item is None:
        return before, [], None

    if target_offer_id is None:
        remaining = [dict(o) for o in active_before if o["offer_id"] != source_offer_id]
        if not remaining:
            return before, [], "Нельзя отключить единственный активный оффер в потоке"
        after = _redistribute_shares_to_100(remaining)
        return before, after, None

    target_name = str(offer_catalog.get(target_offer_id, {}).get("name") or f"Offer #{target_offer_id}")
    existing_target = next((o for o in active_before if o["offer_id"] == target_offer_id), None)
    if existing_target is not None:
        merged: list[dict[str, Any]] = []
        for o in active_before:
            if o["offer_id"] == source_offer_id:
                continue
            item = dict(o)
            if item["offer_id"] == target_offer_id:
                item["share"] += source_item["share"]
            merged.append(item)
        after = _redistribute_shares_to_100(merged)
    else:
        after = []
        for o in active_before:
            if o["offer_id"] == source_offer_id:
                after.append(
                    {
                        "offer_id": target_offer_id,
                        "name": target_name,
                        "share": o["share"],
                        "state": "active",
                    }
                )
            else:
                after.append(dict(o))
        after = _redistribute_shares_to_100(after)

    return before, after, None


@router.post("/bulk", response_model=BulkCampaignCreateResponse)
async def bulk_create_campaigns(
    payload: BulkCampaignCreateRequest,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
) -> BulkCampaignCreateResponse:
    """Массово создаёт кампании из списка (Название, GEO, Offer ID) с независимой обработкой строк."""
    settings = get_settings()
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
    offer_ids = {int(r["id"]) for r in extract_rows(offers_raw) if r.get("id") is not None}

    domain_row = next((r for r in domain_rows if str(r.get("id")) == str(payload.domain_id)), None)
    if domain_row is None:
        raise HTTPException(status_code=422, detail="Выбранный домен не найден в Keitaro")
    if not any(str(r.get("id")) == str(payload.group_id) for r in group_rows):
        raise HTTPException(status_code=422, detail="Выбранная группа кампаний не найдена в Keitaro")
    if not any(str(r.get("id")) == str(payload.traffic_source_id) for r in source_rows):
        raise HTTPException(status_code=422, detail="Выбранный источник трафика не найден в Keitaro")

    base_url = getattr(client, "base_url", None) or settings.keitaro_base_url
    results: list[BulkCampaignResultItem] = []

    for idx, item in enumerate(payload.items):
        effective_name = apply_campaign_name_prefix(item.name, settings.campaign_name_prefix)
        if item.offer_id not in offer_ids:
            err = f"Оффер #{item.offer_id} не найден в Keitaro"
            log_operation(
                db,
                operation="bulk.campaign.create",
                resource_type="campaign",
                resource_id=None,
                summary=f"[Bulk #{idx + 1}] Ошибка создания '{effective_name}': {err}",
                status="error",
                details={"country_code": item.country_code, "offer_id": item.offer_id},
            )
            results.append(
                BulkCampaignResultItem(
                    index=idx,
                    name=effective_name,
                    country_code=item.country_code,
                    offer_id=item.offer_id,
                    status="error",
                    error=err,
                )
            )
            continue

        alias = item.alias or f"cmp-{secrets.token_hex(4)}"
        campaign_id: int | None = None
        try:
            created = await client.create_campaign(
                {
                    "name": effective_name,
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
            await client.create_stream(
                {
                    "campaign_id": campaign_id,
                    "name": f"Geo {item.country_code}",
                    "type": "regular",
                    "position": 1,
                    "schema": "redirect",
                    "action_type": "http",
                    "action_payload": settings.safe_redirect_url,
                    "state": "active",
                    "filters": [{"name": "country", "mode": "accept", "payload": [item.country_code]}],
                }
            )
            await client.create_stream(
                {
                    "campaign_id": campaign_id,
                    "name": "Офферы",
                    "type": "default",
                    "position": 2,
                    "schema": "landings",
                    "action_type": "do_nothing",
                    "state": "active",
                    "offers": [{"offer_id": item.offer_id, "share": 100, "state": "active"}],
                }
            )
            resolved_alias = str(created.get("alias") or alias)
            resolved_name = str(created.get("name") or effective_name)
            log_operation(
                db,
                operation="bulk.campaign.create",
                resource_type="campaign",
                resource_id=campaign_id,
                summary=f"[Bulk] Создана кампания '{resolved_name}' (Geo {item.country_code}, оффер #{item.offer_id})",
                status="success",
                details={"country_code": item.country_code, "offer_id": item.offer_id},
            )
            results.append(
                BulkCampaignResultItem(
                    index=idx,
                    name=resolved_name,
                    country_code=item.country_code,
                    offer_id=item.offer_id,
                    status="success",
                    campaign_id=campaign_id,
                    tracking_url=build_tracking_url(domain_row.get("name"), resolved_alias),
                    keitaro_url=build_keitaro_campaign_url(base_url, campaign_id),
                )
            )
        except (KeitaroError, KeyError, TypeError, ValueError) as exc:
            if campaign_id is not None:
                try:
                    await client.disable_campaign(campaign_id)
                except KeitaroError:
                    pass
            detail = exc.message if isinstance(exc, KeitaroError) else "Ошибка ответа Keitaro"
            log_operation(
                db,
                operation="bulk.campaign.create",
                resource_type="campaign",
                resource_id=campaign_id,
                summary=f"[Bulk] Ошибка создания '{effective_name}': {detail}",
                status="error",
                details={"country_code": item.country_code, "offer_id": item.offer_id},
            )
            results.append(
                BulkCampaignResultItem(
                    index=idx,
                    name=effective_name,
                    country_code=item.country_code,
                    offer_id=item.offer_id,
                    status="error",
                    error=detail,
                )
            )

    succeeded = sum(1 for r in results if r.status == "success")
    return BulkCampaignCreateResponse(
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )


@router.post("/{campaign_id}/clone-geos", response_model=CloneGeosResponse)
async def clone_campaign_to_geos(
    campaign_id: int,
    payload: CloneGeosRequest,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
) -> CloneGeosResponse:
    """Клонирует настройки и потоки кампании на пачку GEO с заменой фильтра страны в Flow 1."""
    settings = get_settings()
    try:
        source_campaign, source_streams_raw, domains_raw = await asyncio.gather(
            client.get_campaign(campaign_id),
            client.list_campaign_streams(campaign_id),
            client.list_domains(),
        )
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    if not isinstance(source_campaign, dict) or source_campaign.get("id") is None:
        raise HTTPException(status_code=404, detail="Исходная кампания не найдена")

    source_streams = sorted(
        extract_rows(source_streams_raw),
        key=lambda s: (int(s["position"]) if s.get("position") is not None else 9999, int(s.get("id") or 0)),
    )
    domain_rows = extract_rows(domains_raw)
    domain_row = next(
        (r for r in domain_rows if str(r.get("id")) == str(source_campaign.get("domain_id"))),
        None,
    )
    base_url = getattr(client, "base_url", None) or settings.keitaro_base_url
    source_name = str(source_campaign.get("name") or f"Campaign #{campaign_id}")

    results: list[CloneGeoResultItem] = []
    for geo in payload.country_codes:
        target_name = apply_campaign_name_prefix(f"{source_name}_{geo}", settings.campaign_name_prefix)
        alias = f"cmp-{secrets.token_hex(4)}"
        new_cid: int | None = None
        try:
            cmp_payload: dict[str, Any] = {
                "name": target_name,
                "alias": alias,
                "type": source_campaign.get("type") or "position",
                "cost_type": source_campaign.get("cost_type") or "CPC",
                "state": "active",
            }
            for key in ("domain_id", "group_id", "traffic_source_id"):
                if source_campaign.get(key) is not None:
                    cmp_payload[key] = int(source_campaign[key])

            created = await client.create_campaign(cmp_payload)
            new_cid = int(created["id"])

            geo_patched = False
            for idx, stream in enumerate(source_streams):
                stream_payload: dict[str, Any] = {
                    "campaign_id": new_cid,
                    "name": stream.get("name") or f"Stream {idx + 1}",
                    "type": stream.get("type") or "regular",
                    "position": stream.get("position") if stream.get("position") is not None else idx + 1,
                    "schema": stream.get("schema") or "landings",
                    "action_type": stream.get("action_type") or "do_nothing",
                    "state": stream.get("state") or "active",
                }
                if stream.get("action_payload") is not None:
                    stream_payload["action_payload"] = stream["action_payload"]

                filters = deepcopy(stream.get("filters") or [])
                is_geo_flow = (not geo_patched) and (
                    any(isinstance(f, dict) and f.get("name") == "country" for f in filters)
                    or stream.get("schema") == "redirect"
                )
                if is_geo_flow:
                    geo_patched = True
                    stream_payload["name"] = f"Geo {geo}"
                    replaced_filter = False
                    for f in filters:
                        if isinstance(f, dict) and f.get("name") == "country":
                            f["mode"] = f.get("mode") or "accept"
                            f["payload"] = [geo]
                            replaced_filter = True
                    if not replaced_filter:
                        filters.append({"name": "country", "mode": "accept", "payload": [geo]})
                if filters:
                    stream_payload["filters"] = filters

                if stream.get("schema") == "landings" and isinstance(stream.get("offers"), list):
                    stream_payload["offers"] = [
                        {
                            "offer_id": int(o["offer_id"]),
                            "share": int(o.get("share") or 0),
                            "state": str(o.get("state") or "active"),
                        }
                        for o in stream["offers"]
                        if isinstance(o, dict) and o.get("offer_id") is not None
                    ]

                await client.create_stream(stream_payload)

            resolved_alias = str(created.get("alias") or alias)
            resolved_name = str(created.get("name") or target_name)
            log_operation(
                db,
                operation="bulk.campaign.clone",
                resource_type="campaign",
                resource_id=new_cid,
                summary=f"Клонирована кампания #{campaign_id} → #{new_cid} '{resolved_name}' (Geo {geo})",
                status="success",
                details={"source_campaign_id": campaign_id, "country_code": geo},
            )
            results.append(
                CloneGeoResultItem(
                    country_code=geo,
                    status="success",
                    campaign_id=new_cid,
                    name=resolved_name,
                    tracking_url=build_tracking_url(
                        domain_row.get("name") if domain_row else source_campaign.get("domain"),
                        resolved_alias,
                    ),
                    keitaro_url=build_keitaro_campaign_url(base_url, new_cid),
                )
            )
        except (KeitaroError, KeyError, TypeError, ValueError) as exc:
            if new_cid is not None:
                try:
                    await client.disable_campaign(new_cid)
                except KeitaroError:
                    pass
            detail = exc.message if isinstance(exc, KeitaroError) else "Ошибка клонирования кампании"
            log_operation(
                db,
                operation="bulk.campaign.clone",
                resource_type="campaign",
                resource_id=new_cid,
                summary=f"Ошибка клонирования кампании #{campaign_id} на {geo}: {detail}",
                status="error",
                details={"source_campaign_id": campaign_id, "country_code": geo},
            )
            results.append(
                CloneGeoResultItem(
                    country_code=geo,
                    status="error",
                    name=target_name,
                    error=detail,
                )
            )

    succeeded = sum(1 for r in results if r.status == "success")
    return CloneGeosResponse(
        source_campaign_id=campaign_id,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )


async def _collect_replace_plan(
    payload: BulkOfferReplaceRequest,
    client: KeitaroClient,
) -> tuple[
    list[BulkReplaceStreamPreview],
    list[BulkReplaceStreamSkipped],
    dict[int, dict[str, Any]],
]:
    try:
        campaigns_raw, offers_raw = await asyncio.gather(
            client.list_campaigns(limit=200, offset=0),
            client.list_offers(),
        )
    except KeitaroError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    offer_catalog: dict[int, dict[str, Any]] = {
        int(r["id"]): r for r in extract_rows(offers_raw) if r.get("id") is not None
    }
    if payload.source_offer_id not in offer_catalog:
        raise HTTPException(status_code=422, detail=f"Исходный оффер #{payload.source_offer_id} не найден")
    if payload.target_offer_id is not None and payload.target_offer_id not in offer_catalog:
        raise HTTPException(status_code=422, detail=f"Целевой оффер #{payload.target_offer_id} не найден")

    target_cids = set(payload.campaign_ids) if payload.campaign_ids else None
    campaigns = [
        r
        for r in extract_rows(campaigns_raw)
        if r.get("id") is not None
        and r.get("state") != "deleted"
        and (target_cids is None or int(r["id"]) in target_cids)
    ]

    semaphore = asyncio.Semaphore(8)

    async def _fetch_streams(cid: int) -> tuple[int, list[dict[str, Any]]]:
        async with semaphore:
            try:
                rows = await client.list_campaign_streams(cid)
                return cid, extract_rows(rows)
            except KeitaroError:
                return cid, []

    fetched = await asyncio.gather(*(_fetch_streams(int(c["id"])) for c in campaigns))
    streams_by_cid = dict(fetched)

    affected: list[BulkReplaceStreamPreview] = []
    skipped: list[BulkReplaceStreamSkipped] = []

    for cmp_row in campaigns:
        cid = int(cmp_row["id"])
        cname = str(cmp_row.get("name") or f"Campaign #{cid}")
        for stream in streams_by_cid.get(cid, []):
            if stream.get("id") is None or stream.get("schema") != "landings":
                continue
            sid = int(stream["id"])
            sname = str(stream.get("name") or f"Stream #{sid}")
            raw_offers_val = stream.get("offers")
            raw_offers: list[dict[str, Any]] = raw_offers_val if isinstance(raw_offers_val, list) else []
            before, after, skip_reason = _compute_stream_replacement(
                raw_offers,
                source_offer_id=payload.source_offer_id,
                target_offer_id=payload.target_offer_id,
                offer_catalog=offer_catalog,
            )
            if skip_reason:
                skipped.append(
                    BulkReplaceStreamSkipped(
                        campaign_id=cid,
                        campaign_name=cname,
                        stream_id=sid,
                        stream_name=sname,
                        reason=skip_reason,
                    )
                )
            elif after:
                affected.append(
                    BulkReplaceStreamPreview(
                        campaign_id=cid,
                        campaign_name=cname,
                        stream_id=sid,
                        stream_name=sname,
                        before=before,
                        after=after,
                        diff=compute_offer_diff(before, after),
                    )
                )

    return affected, skipped, offer_catalog


@router.post("/bulk-offer-replace/preview", response_model=BulkOfferReplacePreviewResponse)
async def preview_bulk_offer_replace(
    payload: BulkOfferReplaceRequest,
    client: KeitaroClient = Depends(get_keitaro_client),
) -> BulkOfferReplacePreviewResponse:
    """Предпросмотр массовой замены или отключения оффера во всех затронутых потоках."""
    affected, skipped, _ = await _collect_replace_plan(payload, client)
    return BulkOfferReplacePreviewResponse(
        source_offer_id=payload.source_offer_id,
        target_offer_id=payload.target_offer_id,
        affected_streams=affected,
        skipped_streams=skipped,
    )


@router.post("/bulk-offer-replace/apply", response_model=BulkOfferReplaceApplyResponse)
async def apply_bulk_offer_replace(
    payload: BulkOfferReplaceRequest,
    db: Session = Depends(get_db),
    client: KeitaroClient = Depends(get_keitaro_client),
) -> BulkOfferReplaceApplyResponse:
    """Применяет массовую замену/отключение оффера в Keitaro с записью diff в журнал операций."""
    affected, skipped, _ = await _collect_replace_plan(payload, client)
    results: list[BulkOfferReplaceApplyResult] = []

    for item in affected:
        keitaro_offers = [
            {"offer_id": int(o["offer_id"]), "share": int(o["share"]), "state": str(o["state"])} for o in item.after
        ]
        try:
            await client.update_stream(item.stream_id, {"offers": keitaro_offers})
            upsert_stream_snapshots(
                db,
                campaign_id=item.campaign_id,
                stream_id=item.stream_id,
                offers=item.before + item.after,
            )
            action_label = (
                f"замена #{payload.source_offer_id} → #{payload.target_offer_id}"
                if payload.target_offer_id is not None
                else f"отключение #{payload.source_offer_id}"
            )
            log_operation(
                db,
                operation="bulk.offer.replace",
                resource_type="stream",
                resource_id=item.stream_id,
                summary=f"[Bulk] Поток #{item.stream_id} (кампания #{item.campaign_id}): {action_label}",
                status="success",
                details={
                    "campaign_id": item.campaign_id,
                    "stream_id": item.stream_id,
                    "source_offer_id": payload.source_offer_id,
                    "target_offer_id": payload.target_offer_id,
                    "offers": keitaro_offers,
                    "before": item.before,
                    "after": item.after,
                    "diff": item.diff,
                },
            )
            results.append(
                BulkOfferReplaceApplyResult(
                    campaign_id=item.campaign_id,
                    campaign_name=item.campaign_name,
                    stream_id=item.stream_id,
                    stream_name=item.stream_name,
                    status="success",
                )
            )
        except KeitaroError as exc:
            log_operation(
                db,
                operation="bulk.offer.replace",
                resource_type="stream",
                resource_id=item.stream_id,
                summary=f"[Bulk] Ошибка обновления потока #{item.stream_id}: {exc.message}",
                status="error",
                details={
                    "campaign_id": item.campaign_id,
                    "stream_id": item.stream_id,
                    "before": item.before,
                    "after": item.after,
                    "diff": item.diff,
                },
            )
            results.append(
                BulkOfferReplaceApplyResult(
                    campaign_id=item.campaign_id,
                    campaign_name=item.campaign_name,
                    stream_id=item.stream_id,
                    stream_name=item.stream_name,
                    status="error",
                    error=exc.message,
                )
            )

    succeeded = sum(1 for r in results if r.status == "success")
    return BulkOfferReplaceApplyResponse(
        source_offer_id=payload.source_offer_id,
        target_offer_id=payload.target_offer_id,
        total_streams=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
        skipped_streams=skipped,
    )
