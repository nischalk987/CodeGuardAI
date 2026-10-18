"""Strict Pydantic schema used to validate model output."""

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Severity


class ModelFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    rule_id: str = Field(min_length=1, max_length=80)
    severity: Severity
    category: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    file_path: str = Field(min_length=1, max_length=512)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    confidence: int = Field(ge=0, le=100)
    evidence: str = Field(min_length=1, max_length=2_000)
    suggested_fix: str = Field(min_length=1, max_length=2_000)


class ModelReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    findings: list[ModelFinding] = Field(max_length=25)


# Keep this inline and deliberately small: Groq strict structured outputs support a subset of
# JSON Schema, and this avoids $ref/$defs emitted for Python enum models.
RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "rule_id": {"type": "string"},
                    "severity": {"type": "string", "enum": [item.value for item in Severity]},
                    "category": {"type": "string"},
                    "message": {"type": "string"},
                    "file_path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "confidence": {"type": "integer"},
                    "evidence": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": [
                    "rule_id",
                    "severity",
                    "category",
                    "message",
                    "file_path",
                    "start_line",
                    "end_line",
                    "confidence",
                    "evidence",
                    "suggested_fix",
                ],
            },
        }
    },
    "required": ["findings"],
}
