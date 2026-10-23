from typing import Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["critical", "high", "medium", "low"]
FindingSource = Literal["static", "ai"]
AIReviewStatus = Literal["disabled", "pending", "completed", "unavailable", "failed"]
SUPPORTED_REVIEW_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Finding(BaseModel):
    id: str
    severity: Severity
    category: str
    file_path: str
    line: int = Field(ge=1)
    title: str
    message: str
    explanation: str
    suggested_fix: str
    source: FindingSource
    confidence: int = Field(ge=0, le=100)
    # Additional persisted-domain metadata; optional to preserve the existing dashboard contract.
    status: Literal["open", "accepted", "dismissed", "fixed"] = "open"
    rule_id: str | None = None
    end_line: int | None = Field(default=None, ge=1)
    evidence: str | None = None
    analyzer_name: str | None = None
    analyzer_version: str | None = None
    certainty: Literal["confirmed", "hypothesis"] | None = None


class ReviewSummary(BaseModel):
    critical: int = Field(ge=0)
    high: int = Field(ge=0)
    medium: int = Field(ge=0)
    low: int = Field(ge=0)
    total_findings: int = Field(ge=0)


class Review(BaseModel):
    review_id: str
    repository: str
    branch: str
    status: Literal["queued", "running", "completed", "failed"]
    risk_score: int = Field(ge=0, le=100)
    summary: ReviewSummary
    findings: list[Finding]
    correlation_id: str | None = None
    failure_reason: str | None = None
    ai_review_requested: bool = False
    ai_review_status: AIReviewStatus = "disabled"
    ai_review_message: str | None = None


class ReviewCreateRequest(BaseModel):
    """A bounded source snippet; source is treated as untrusted data."""

    model_config = {"extra": "forbid"}

    source_code: str = Field(min_length=1, max_length=40_000)
    file_path: str = Field(default="snippet.py", min_length=1, max_length=240)
    repository: str = Field(default="local", min_length=1, max_length=200)
    branch: str = Field(default="local", min_length=1, max_length=255)
    ai_review: bool = Field(default=False, description="Opt in to an additional hosted AI analysis.")

    @field_validator("source_code")
    @classmethod
    def bound_source_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 40_000:
            raise ValueError("source_code exceeds the 40000 byte limit")
        return value

    @field_validator("file_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        from pathlib import PurePosixPath

        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            path.is_absolute()
            or any(part in {".", ".."} for part in path.parts)
            or any(ord(character) < 32 for character in normalized)
        ):
            raise ValueError("file_path must be a safe repository-relative path")
        if not path.suffix:
            raise ValueError("file_path must include a supported source file extension")
        if path.suffix.lower() not in SUPPORTED_REVIEW_SUFFIXES:
            raise ValueError("file_path must use a supported source extension")
        return path.as_posix()
