import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_load_environment_and_normalize_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test API")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://dashboard.example/")
    monkeypatch.setenv("CORS_ORIGINS", '["https://dashboard.example", "https://preview.example/"]')

    settings = Settings(_env_file=None)

    assert settings.app_name == "Test API"
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.allowed_origins == ["https://dashboard.example", "https://preview.example"]


def test_production_requires_an_explicit_frontend_origin() -> None:
    with pytest.raises(ValidationError, match="FRONTEND_ORIGIN or CORS_ORIGINS"):
        Settings(_env_file=None, environment="production")


def test_invalid_environment_and_log_level_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="staging")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="TRACE")  # type: ignore[arg-type]


def test_development_uses_local_frontend_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.allowed_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_invalid_cors_origins_are_rejected() -> None:
    with pytest.raises(ValidationError, match="origins without paths"):
        Settings(_env_file=None, cors_origins=["https://dashboard.example/app"])
