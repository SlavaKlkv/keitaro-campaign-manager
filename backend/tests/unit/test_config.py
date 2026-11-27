"""Unit-тесты конфигурации и нормализации KEITARO_BASE_URL."""

import pytest

from app.config import Settings
from app.keitaro_helpers import build_keitaro_campaign_url


@pytest.mark.parametrize(
    ("raw_url", "expected"),
    [
        ("https://keitaro.example.com", "https://keitaro.example.com"),
        ("https://keitaro.example.com/", "https://keitaro.example.com"),
        ("https://keitaro.example.com/admin", "https://keitaro.example.com"),
        ("https://keitaro.example.com/admin/", "https://keitaro.example.com"),
        ("https://keitaro.example.com/admin_api", "https://keitaro.example.com"),
        ("https://keitaro.example.com/admin_api/v1/", "https://keitaro.example.com"),
        ("  https://keitaro.example.com/ADMIN/  ", "https://keitaro.example.com"),
    ],
)
def test_normalize_keitaro_base_url(raw_url: str, expected: str) -> None:
    """Проверяет удаление хвостовых путей /admin и /admin_api(/v1)."""
    settings = Settings(keitaro_base_url=raw_url, _env_file=None)
    assert settings.keitaro_base_url == expected


def test_cors_origins_list_parsing() -> None:
    """Проверяет разбор списка CORS origin из строки."""
    settings = Settings(
        cors_origins="http://localhost:5173, http://127.0.0.1:5173 , ",
        _env_file=None,
    )
    assert settings.cors_origins_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@pytest.mark.parametrize(
    ("base_url", "campaign_id", "expected"),
    [
        ("https://keitaro.example.com", 55, "https://keitaro.example.com/admin/#!/campaigns/55"),
        ("https://keitaro.example.com/", 55, "https://keitaro.example.com/admin/#!/campaigns/55"),
        ("https://keitaro.example.com/admin_api/v1", 55, "https://keitaro.example.com/admin/#!/campaigns/55"),
        ("https://keitaro.example.com/admin/", 55, "https://keitaro.example.com/admin/#!/campaigns/55"),
        ("", 55, None),
        ("   ", 55, None),
        (None, 55, None),
    ],
)
def test_build_keitaro_campaign_url(
    base_url: str | None,
    campaign_id: int,
    expected: str | None,
) -> None:
    """Проверяет формирование ссылки VIEW IN KT и возврат None при пустом base_url."""
    assert build_keitaro_campaign_url(base_url, campaign_id) == expected


def test_optional_defaults_and_safe_redirect_parsing() -> None:
    """Пустые строки для DEFAULT_*_ID приводятся к None, а пустой SAFE_REDIRECT_URL — к google.com."""
    settings = Settings(
        default_domain_id="",  # type: ignore[arg-type]
        default_group_id="  ",  # type: ignore[arg-type]
        default_traffic_source_id="31",  # type: ignore[arg-type]
        safe_redirect_url="  ",
        _env_file=None,
    )
    assert settings.default_domain_id is None
    assert settings.default_group_id is None
    assert settings.default_traffic_source_id == 31
    assert settings.safe_redirect_url == "https://google.com"
