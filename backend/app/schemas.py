"""Pydantic-схемы запросов и ответов API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DomainItem(BaseModel):
    """Краткое описание домена из Keitaro."""

    id: int
    name: str
    status: str | None = None
    is_ssl: bool | None = None
    state: str | None = None


class GroupItem(BaseModel):
    """Группа кампаний из Keitaro."""

    id: int
    name: str
    type: str | None = None


class TrafficSourceItem(BaseModel):
    """Источник трафика из Keitaro."""

    id: int
    name: str
    template_name: str | None = None
    state: str | None = None


class OfferItem(BaseModel):
    """Оффер из каталога Keitaro."""

    id: int
    name: str
    group_id: int | None = None
    group: str | None = None
    state: str | None = None
    country: list[str] = Field(default_factory=list)


class MetaResponse(BaseModel):
    """Справочники Keitaro для форм создаватора и редактора."""

    domains: list[DomainItem]
    groups: list[GroupItem]
    traffic_sources: list[TrafficSourceItem]
    offers: list[OfferItem]
    keitaro_base_url: str
    defaults: dict[str, int | None]


class CampaignSummary(BaseModel):
    """Элемент списка кампаний."""

    id: int
    name: str
    alias: str | None = None
    state: str | None = None
    domain_id: int | None = None
    domain: str | None = None
    group_id: int | None = None
    group: str | None = None
    traffic_source_id: int | None = None
    type: str | None = None
    cost_type: str | None = None
    keitaro_url: str


class CampaignCreateRequest(BaseModel):
    """Запрос на создание кампании с двумя потоками (Geo redirect + Offer)."""

    name: str = Field(min_length=1, max_length=120)
    country_code: str = Field(min_length=2, max_length=2, pattern="^[A-Za-z]{2}$")
    offer_id: int = Field(gt=0)
    domain_id: int = Field(gt=0)
    group_id: int = Field(gt=0)
    traffic_source_id: int = Field(gt=0)
    alias: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern="^[a-zA-Z0-9_-]+$",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Обрезает пробелы и запрещает пустое имя."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Название кампании не должно быть пустым")
        return cleaned

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        """Приводит двухбуквенный ISO-код страны к верхнему регистру."""
        return value.strip().upper()


class CampaignCreateResponse(BaseModel):
    """Результат создания кампании в Keitaro."""

    id: int
    name: str
    alias: str
    country_code: str
    offer_id: int
    domain_id: int
    group_id: int
    traffic_source_id: int
    streams_created: int
    tracking_url: str | None = None
    keitaro_url: str


class OperationLogItem(BaseModel):
    """Запись журнала операций."""

    id: int
    operation: str
    resource_type: str
    resource_id: int | None
    summary: str
    status: str
    details: dict[str, Any] | None = None
    created_at: datetime
