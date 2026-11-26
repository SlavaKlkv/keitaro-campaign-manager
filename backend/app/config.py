"""Конфигурация приложения через переменные окружения и файл .env."""

from functools import lru_cache
import re

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки сервиса, считываемые из окружения или корневого .env."""

    app_name: str = "Keitaro Campaign Manager"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/keitaro_manager"
    keitaro_base_url: str = ""
    keitaro_api_key: SecretStr = SecretStr("")
    keitaro_timeout_seconds: float = 20.0
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("keitaro_base_url")
    @classmethod
    def normalize_keitaro_base_url(cls, value: str) -> str:
        """Удаляет хвостовые слэши и суффиксы /admin, /admin_api, /admin_api/v1."""
        cleaned = value.strip().rstrip("/")
        cleaned = re.sub(r"(/admin_api(/v\d+)?|/admin)+$", "", cleaned, flags=re.IGNORECASE)
        return cleaned.rstrip("/")

    @property
    def cors_origins_list(self) -> list[str]:
        """Возвращает список разрешённых origin для CORS."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Кэшированный доступ к настройкам приложения."""
    return Settings()
