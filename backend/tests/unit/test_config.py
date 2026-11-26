"""Unit-тесты конфигурации и нормализации KEITARO_BASE_URL."""

import pytest

from app.config import Settings


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
