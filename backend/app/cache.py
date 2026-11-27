"""In-memory кэш справочников Keitaro с настраиваемым TTL."""

from dataclasses import dataclass
from datetime import UTC, datetime
import time
from typing import Any


@dataclass
class _CacheEntry:
    """Элемент кэша со временем создания и истечения."""

    key: str
    value: Any
    cached_at: datetime
    expires_at: float


class MetaCache:
    """Простой потокобезопасный (в рамках event loop) TTL-кэш для /api/meta."""

    def __init__(self) -> None:
        self._entry: _CacheEntry | None = None

    def get(self, key: str) -> tuple[Any, datetime] | None:
        """Возвращает сохранённое значение и время кэширования, если TTL ещё не истёк."""
        if self._entry is None or self._entry.key != key:
            return None
        if time.monotonic() >= self._entry.expires_at:
            self._entry = None
            return None
        return self._entry.value, self._entry.cached_at

    def set(self, key: str, value: Any, ttl_seconds: int) -> datetime:
        """Сохраняет значение в кэш на указанный TTL и возвращает timestamp."""
        now = datetime.now(UTC)
        if ttl_seconds <= 0:
            self._entry = None
            return now
        self._entry = _CacheEntry(
            key=key,
            value=value,
            cached_at=now,
            expires_at=time.monotonic() + ttl_seconds,
        )
        return now

    def invalidate(self) -> None:
        """Принудительно очищает кэш справочников."""
        self._entry = None


meta_cache = MetaCache()
