from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low"]
FindingSource = Literal["static", "ai"]


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
