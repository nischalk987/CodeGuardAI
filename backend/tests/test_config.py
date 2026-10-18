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
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_provider="openai")  # type: ignore[arg-type]


def test_development_uses_local_frontend_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.allowed_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_invalid_cors_origins_are_rejected() -> None:
    with pytest.raises(ValidationError, match="origins without paths"):
        Settings(_env_file=None, cors_origins=["https://dashboard.example/app"])


def test_groq_settings_load_from_environment_without_exposing_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_key = "gsk_test_only_do_not_use"
    monkeypatch.setenv("GROQ_API_KEY", test_key)
    monkeypatch.setenv("GROQ_MODEL", "test/model")
    monkeypatch.setenv("GROQ_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("GROQ_MAX_RETRIES", "1")
    monkeypatch.setenv("AI_REVIEW_MAX_INPUT_BYTES", "8192")

    settings = Settings(_env_file=None)

    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == test_key
    assert settings.groq_model == "test/model"
    assert settings.groq_timeout_seconds == 7.5
    assert settings.groq_max_retries == 1
    assert settings.ai_review_max_input_bytes == 8192
    assert test_key not in repr(settings)
    assert test_key not in settings.model_dump_json()


def test_ai_provider_defaults_to_groq_and_huggingface_settings_are_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "hf_test_only_do_not_use"
    monkeypatch.setenv("AI_PROVIDER", "huggingface")
    monkeypatch.setenv("HF_TOKEN", token)
    monkeypatch.setenv("HF_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("HF_TIMEOUT_SECONDS", "9.5")
    monkeypatch.setenv("HF_MAX_RETRIES", "1")

    settings = Settings(_env_file=None)

    assert settings.ai_provider == "huggingface"
    assert settings.hf_token is not None
    assert settings.hf_token.get_secret_value() == token
    assert settings.hf_model == "openai/gpt-oss-20b"
    assert settings.hf_timeout_seconds == 9.5
    assert settings.hf_max_retries == 1
    assert token not in repr(settings)
    assert token not in settings.model_dump_json()


def test_ai_provider_defaults_to_groq_without_provider_environment(monkeypatch) -> None:
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    assert Settings(_env_file=None).ai_provider == "groq"


def test_blank_groq_key_is_treated_as_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "   ")
    assert Settings(_env_file=None).groq_api_key is None


def test_database_url_is_secret_and_validated() -> None:
    value = "postgresql://review_user:private_password@db.example/neondb?sslmode=require"
    settings = Settings(_env_file=None, database_url=value)

    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == value
    assert "private_password" not in repr(settings)
    assert "private_password" not in settings.model_dump_json()


def test_redis_url_is_validated_and_secret() -> None:
    value = "rediss://review_user:private_password@redis.example:6380/0"
    settings = Settings(_env_file=None, redis_url=value)

    assert settings.redis_url.get_secret_value() == value
    assert "private_password" not in repr(settings)
    assert "private_password" not in settings.model_dump_json()


@pytest.mark.parametrize("value", ["", "http://redis.example", "redis:///0"])
def test_invalid_redis_urls_are_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, redis_url=value)


@pytest.mark.parametrize(
    "value",
    ["", "https://db.example/neondb", "postgresql://db.example", "postgresql://db.example/"],
)
def test_invalid_database_urls_are_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"groq_model": " "},
        {"hf_model": " "},
        {"hf_timeout_seconds": 0},
        {"hf_timeout_seconds": 121},
        {"hf_max_retries": -1},
        {"hf_max_retries": 4},
        {"groq_timeout_seconds": 0},
        {"groq_timeout_seconds": 121},
        {"groq_max_retries": -1},
        {"groq_max_retries": 4},
        {"ai_review_max_input_bytes": 0},
        {"ai_review_max_input_bytes": 200_001},
    ],
)
def test_invalid_ai_review_settings_are_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)
