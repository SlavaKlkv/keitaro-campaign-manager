"""Вспомогательные функции нормализации ответов Keitaro API."""

from typing import Any


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    """Приводит ответ Keitaro (список или обёртку со списком) к списку словарей."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("campaigns", "streams", "offers", "data", "items"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [row for row in candidate if isinstance(row, dict)]
    return []


def build_keitaro_campaign_url(base_url: str, campaign_id: int) -> str:
    """Формирует прямую ссылку на кампанию в веб-интерфейсе Keitaro."""
    clean = base_url.rstrip("/")
    return f"{clean}/admin/#!/campaigns/{campaign_id}"


def build_tracking_url(domain_name: str | None, alias: str | None) -> str | None:
    """Собирает публичный tracking URL кампании из домена и алиаса."""
    if not domain_name or not alias:
        return None
    clean_domain = domain_name.strip().rstrip("/")
    if not clean_domain.startswith(("http://", "https://")):
        clean_domain = f"https://{clean_domain}"
    return f"{clean_domain}/{alias.lstrip('/')}"


def pick_default_id(rows: list[dict[str, Any]], preferred_names: tuple[str, ...] = ()) -> int | None:
    """Выбирает ID по умолчанию: сначала по предпочтительному имени, затем первый active, затем первый элемент."""
    if not rows:
        return None
    lowered = {name.lower() for name in preferred_names}
    if lowered:
        for row in rows:
            if str(row.get("name", "")).strip().lower() in lowered and row.get("id") is not None:
                return int(row["id"])
    for row in rows:
        if row.get("state") == "active" and row.get("id") is not None:
            return int(row["id"])
    for row in rows:
        if row.get("id") is not None:
            return int(row["id"])
    return None
