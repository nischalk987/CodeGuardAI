from functools import lru_cache
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated settings for the API process.

    Environment variables take precedence over the optional local ``.env`` file.
    Provider credentials are optional and remain backend-only.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_name: str = Field(default="CodeGuard AI API", validation_alias="APP_NAME", min_length=1)
    environment: Literal["development", "test", "production"] = Field(
        default="development", validation_alias="ENVIRONMENT"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )
    frontend_origin: str | None = Field(default=None, validation_alias="FRONTEND_ORIGIN")
    cors_origins: list[str] = Field(default_factory=list, validation_alias="CORS_ORIGINS")
    groq_api_key: SecretStr | None = Field(
        default=None, validation_alias="GROQ_API_KEY", repr=False
    )
    database_url: SecretStr | None = Field(
        default=None, validation_alias="DATABASE_URL", repr=False
    )
    groq_model: str = Field(
        default="openai/gpt-oss-20b", validation_alias="GROQ_MODEL", min_length=1, max_length=128
    )
    groq_timeout_seconds: float = Field(
        default=20.0, validation_alias="GROQ_TIMEOUT_SECONDS", gt=0, le=120
    )
    groq_max_retries: int = Field(default=2, validation_alias="GROQ_MAX_RETRIES", ge=0, le=3)
    ai_review_max_input_bytes: int = Field(
        default=40_000, validation_alias="AI_REVIEW_MAX_INPUT_BYTES", ge=1, le=200_000
    )

    @field_validator("groq_api_key", mode="before")
    @classmethod
    def normalize_groq_api_key(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        try:
            parsed = urlsplit(value.strip())
            hostname = parsed.hostname
            database = unquote(parsed.path.lstrip("/"))
        except ValueError:
            raise ValueError("DATABASE_URL must be a valid PostgreSQL URL") from None
        if (
            parsed.scheme not in {"postgresql", "postgresql+psycopg"}
            or not hostname
            or not database
        ):
            raise ValueError("DATABASE_URL must point to a PostgreSQL database")
        return value.strip()

    @field_validator("groq_model")
    @classmethod
    def normalize_groq_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("GROQ_MODEL must not be blank")
        return normalized

    @field_validator("frontend_origin")
    @classmethod
    def normalize_frontend_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        if not _is_origin(normalized):
            raise ValueError("FRONTEND_ORIGIN must be an HTTP(S) origin without a path")
        return normalized

    @field_validator("cors_origins")
    @classmethod
    def normalize_cors_origins(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().rstrip("/") for value in values]
        if any(not _is_origin(value) for value in normalized):
            raise ValueError("CORS_ORIGINS entries must be HTTP(S) origins without paths")
        return normalized

    @model_validator(mode="after")
    def validate_production_origins(self) -> "Settings":
        if self.environment == "production" and not (self.frontend_origin or self.cors_origins):
            raise ValueError("Set FRONTEND_ORIGIN or CORS_ORIGINS when ENVIRONMENT=production")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        configured = [*self.cors_origins]
        if self.frontend_origin:
            configured.append(self.frontend_origin)
        if not configured and self.environment != "production":
            configured = ["http://localhost:5173", "http://127.0.0.1:5173"]
        # Preserve order while avoiding duplicate origin entries.
        return list(dict.fromkeys(origin.rstrip("/") for origin in configured))


def _is_origin(value: str) -> bool:
    if not value:
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not (
        parsed.path or parsed.query or parsed.fragment
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings singleton."""
    return Settings()
