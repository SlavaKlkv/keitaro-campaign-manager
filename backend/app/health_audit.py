"""Аудит здоровья кампаний и потоков (Pre-flight / Health Audit)."""

from typing import Any

from app.schemas import CampaignHealthSummary, HealthIssue


def audit_campaign_streams(
    streams_raw: list[dict[str, Any]],
    offer_catalog: dict[int, dict[str, Any]],
) -> CampaignHealthSummary:
    """Проверяет потоки кампании на типовые ошибки: пустой поток, архивный оффер, дубли, сумма != 100%."""
    issues: list[HealthIssue] = []

    for stream in streams_raw:
        if stream.get("id") is None or stream.get("state") == "disabled":
            continue
        if stream.get("schema") != "landings":
            continue

        stream_id = int(stream["id"])
        stream_name = str(stream.get("name") or f"Stream #{stream_id}")
        raw_offers_val = stream.get("offers")
        raw_offers: list[Any] = raw_offers_val if isinstance(raw_offers_val, list) else []

        seen_ids: set[int] = set()
        duplicate_ids: set[int] = set()
        active_shares: list[int] = []

        for item in raw_offers:
            if not isinstance(item, dict) or item.get("offer_id") is None:
                continue
            oid = int(item["offer_id"])
            state = str(item.get("state") or "active")

            if oid in seen_ids:
                duplicate_ids.add(oid)
            seen_ids.add(oid)

            if state == "active":
                active_shares.append(int(item.get("share") or 0))

            catalog_entry = offer_catalog.get(oid)
            if catalog_entry is None or catalog_entry.get("state") in ("archived", "deleted", "disabled"):
                offer_state = catalog_entry.get("state") if catalog_entry else "deleted"
                issues.append(
                    HealthIssue(
                        code="archived_or_deleted_offer",
                        severity="error" if state == "active" else "warning",
                        stream_id=stream_id,
                        message=(
                            f"Поток «{stream_name}» (#{stream_id}): оффер #{oid} "
                            f"имеет статус '{offer_state}' в каталоге Keitaro."
                        ),
                    )
                )

        if duplicate_ids:
            dup_list = ", ".join(f"#{oid}" for oid in sorted(duplicate_ids))
            issues.append(
                HealthIssue(
                    code="duplicate_offers",
                    severity="error",
                    stream_id=stream_id,
                    message=f"Поток «{stream_name}» (#{stream_id}): дубликаты офферов ({dup_list}).",
                )
            )

        if not active_shares:
            issues.append(
                HealthIssue(
                    code="no_active_offers",
                    severity="error",
                    stream_id=stream_id,
                    message=f"Поток «{stream_name}» (#{stream_id}): нет ни одного активного оффера.",
                )
            )
        else:
            total_share = sum(active_shares)
            if total_share != 100:
                issues.append(
                    HealthIssue(
                        code="invalid_share_sum",
                        severity="error",
                        stream_id=stream_id,
                        message=(
                            f"Поток «{stream_name}» (#{stream_id}): сумма долей активных "
                            f"офферов равна {total_share}% вместо 100%."
                        ),
                    )
                )

    if any(i.severity == "error" for i in issues):
        overall = "error"
    elif issues:
        overall = "warning"
    else:
        overall = "ok"

    return CampaignHealthSummary(status=overall, issues=issues)
