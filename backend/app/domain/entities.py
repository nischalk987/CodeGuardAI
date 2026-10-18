"""Immutable, framework-independent review and finding entities."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

from app.domain.enums import (
    EvidenceCertainty,
    FindingSource,
    FindingStatus,
    ReviewSourceType,
    ReviewStatus,
    Severity,
)
from app.domain.exceptions import InvalidReviewTransition


def _enum_value(enum_type: type, value: object, field_name: str):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value


def stable_finding_id(
    *,
    rule_id: str,
    source: FindingSource,
    file_path: str,
    start_line: int,
    end_line: int,
) -> str:
    """Return a deterministic ID for the same rule, provenance, and source location."""
    identity = {
        "rule_id": _required_text(rule_id, "rule_id"),
        "source": _enum_value(FindingSource, source, "source").value,
        "file_path": _normalize_path(file_path),
        "start_line": start_line,
        "end_line": end_line,
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"fnd_{hashlib.sha256(payload).hexdigest()[:24]}"


def _normalize_path(file_path: str) -> str:
    path = _required_text(file_path, "file_path").replace("\\", "/")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ValueError("file_path must be repository-relative")
    normalized = str(PurePosixPath(path))
    if normalized in {".", ".."} or normalized.startswith("../"):
        raise ValueError("file_path must not escape the repository")
    return normalized


@dataclass(frozen=True, slots=True)
class Finding:
    """One validated observation from a static analyzer or AI reviewer."""

    rule_id: str
    source: FindingSource
    severity: Severity
    category: str
    message: str
    file_path: str
    start_line: int
    end_line: int
    confidence: int
    evidence: str
    suggested_fix: str | None = None
    status: FindingStatus = FindingStatus.OPEN
    certainty: EvidenceCertainty | None = None
    id: str = ""
    analyzer_name: str | None = None
    analyzer_version: str | None = None

    def __post_init__(self) -> None:
        source = _enum_value(FindingSource, self.source, "source")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "severity", _enum_value(Severity, self.severity, "severity"))
        object.__setattr__(self, "status", _enum_value(FindingStatus, self.status, "status"))
        certainty = self.certainty
        if certainty is None:
            certainty = (
                EvidenceCertainty.HYPOTHESIS
                if source is FindingSource.AI
                else EvidenceCertainty.CONFIRMED
            )
        object.__setattr__(
            self, "certainty", _enum_value(EvidenceCertainty, certainty, "certainty")
        )

        object.__setattr__(self, "rule_id", _required_text(self.rule_id, "rule_id"))
        object.__setattr__(self, "category", _required_text(self.category, "category"))
        object.__setattr__(self, "message", _required_text(self.message, "message"))
        object.__setattr__(self, "file_path", _normalize_path(self.file_path))
        object.__setattr__(self, "evidence", _required_text(self.evidence, "evidence"))
        if self.analyzer_name is not None:
            object.__setattr__(self, "analyzer_name", _required_text(self.analyzer_name, "analyzer_name"))
        if self.analyzer_version is not None:
            object.__setattr__(self, "analyzer_version", _required_text(self.analyzer_version, "analyzer_version"))
        if self.suggested_fix is not None:
            object.__setattr__(self, "suggested_fix", _required_text(self.suggested_fix, "suggested_fix"))
        if not isinstance(self.start_line, int) or isinstance(self.start_line, bool) or self.start_line < 1:
            raise ValueError("start_line must be an integer greater than or equal to 1")
        if not isinstance(self.end_line, int) or isinstance(self.end_line, bool) or self.end_line < self.start_line:
            raise ValueError("end_line must be an integer greater than or equal to start_line")
        if not isinstance(self.confidence, int) or isinstance(self.confidence, bool) or not 0 <= self.confidence <= 100:
            raise ValueError("confidence must be an integer between 0 and 100")

        generated_id = stable_finding_id(
            rule_id=self.rule_id,
            source=source,
            file_path=self.file_path,
            start_line=self.start_line,
            end_line=self.end_line,
        )
        if self.id and self.id != generated_id:
            raise ValueError("id must match the deterministic finding identity")
        object.__setattr__(self, "id", generated_id)


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    """Human-readable review summary plus severity totals."""

    text: str = ""
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    total_findings: int = 0

    def __post_init__(self) -> None:
        for name in ("critical", "high", "medium", "low", "total_findings"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.total_findings != self.critical + self.high + self.medium + self.low:
            raise ValueError("total_findings must equal the sum of severity counts")

    @classmethod
    def from_findings(cls, findings: tuple[Finding, ...], text: str = "") -> ReviewSummary:
        counts = {severity.value: 0 for severity in Severity}
        for finding in findings:
            counts[finding.severity.value] += 1
        return cls(text=text, **counts, total_findings=len(findings))


@dataclass(frozen=True, slots=True)
class Review:
    """A review snapshot with explicitly guarded, immutable lifecycle transitions."""

    id: str
    source_type: ReviewSourceType
    repository: str | None = None
    ref: str | None = None
    status: ReviewStatus = ReviewStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone(timedelta(0))))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone(timedelta(0))))
    completed_at: datetime | None = None
    correlation_id: str | None = None
    failure_reason: str | None = None
    summary: ReviewSummary = field(default_factory=ReviewSummary)
    findings: tuple[Finding, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, "id"))
        object.__setattr__(
            self, "source_type", _enum_value(ReviewSourceType, self.source_type, "source_type")
        )
        object.__setattr__(self, "status", _enum_value(ReviewStatus, self.status, "status"))
        if self.repository is not None:
            object.__setattr__(self, "repository", _required_text(self.repository, "repository"))
        if self.ref is not None:
            object.__setattr__(self, "ref", _required_text(self.ref, "ref"))
        created_at = _aware(self.created_at, "created_at")
        updated_at = _aware(self.updated_at, "updated_at")
        if updated_at < created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if self.completed_at is not None:
            completed_at = _aware(self.completed_at, "completed_at")
            if self.status is not ReviewStatus.COMPLETED:
                raise ValueError("completed_at is only valid for completed reviews")
            if completed_at < created_at or completed_at > updated_at:
                raise ValueError("completed_at must be between created_at and updated_at")
        elif self.status is ReviewStatus.COMPLETED:
            raise ValueError("completed reviews require completed_at")
        if self.correlation_id is not None:
            object.__setattr__(self, "correlation_id", _required_text(self.correlation_id, "correlation_id"))
        if self.failure_reason is not None:
            object.__setattr__(self, "failure_reason", _required_text(self.failure_reason, "failure_reason"))
        if self.status is ReviewStatus.FAILED and not self.failure_reason:
            raise ValueError("failed reviews require a safe failure_reason")
        if self.status is not ReviewStatus.FAILED and self.failure_reason is not None:
            raise ValueError("failure_reason is only valid for failed reviews")

        findings = tuple(self.findings)
        if not all(isinstance(item, Finding) for item in findings):
            raise ValueError("findings must contain Finding entities")
        object.__setattr__(self, "findings", findings)
        if not isinstance(self.summary, ReviewSummary):
            raise TypeError("summary must be a ReviewSummary")
        expected_summary = ReviewSummary.from_findings(findings, self.summary.text)
        if self.summary != expected_summary:
            raise ValueError("summary severity counts must match findings")

    def start(self, *, at: datetime | None = None) -> Review:
        return self.transition_to(ReviewStatus.RUNNING, at=at)

    def complete(self, *, at: datetime | None = None, summary: str | None = None) -> Review:
        return self.transition_to(ReviewStatus.COMPLETED, at=at, summary=summary)

    def fail(
        self,
        *,
        at: datetime | None = None,
        reason: str = "The review could not be completed. Please try again.",
    ) -> Review:
        return self.transition_to(ReviewStatus.FAILED, at=at, failure_reason=reason)

    def requeue(self, *, at: datetime | None = None) -> Review:
        """Return a running review to the queue after a retryable execution failure."""
        return self.transition_to(ReviewStatus.QUEUED, at=at)

    def transition_to(
        self,
        status: ReviewStatus,
        *,
        at: datetime | None = None,
        summary: str | None = None,
        failure_reason: str | None = None,
    ) -> Review:
        target = _enum_value(ReviewStatus, status, "status")
        allowed = {
            ReviewStatus.QUEUED: {ReviewStatus.RUNNING, ReviewStatus.FAILED},
            ReviewStatus.RUNNING: {
                ReviewStatus.QUEUED,
                ReviewStatus.COMPLETED,
                ReviewStatus.FAILED,
            },
            ReviewStatus.COMPLETED: set(),
            ReviewStatus.FAILED: set(),
        }
        if target not in allowed[self.status]:
            raise InvalidReviewTransition(
                f"Cannot transition review from {self.status.value} to {target.value}"
            )
        transition_time = _aware(at or datetime.now(timezone(timedelta(0))), "transition time")
        if transition_time < self.updated_at:
            raise ValueError("transition time cannot be earlier than updated_at")
        changes: dict[str, object] = {"status": target, "updated_at": transition_time}
        if target is ReviewStatus.COMPLETED:
            changes["completed_at"] = transition_time
        if target is ReviewStatus.FAILED:
            changes["failure_reason"] = _required_text(
                failure_reason or "The review could not be completed. Please try again.",
                "failure_reason",
            )
        if summary is not None:
            changes["summary"] = ReviewSummary.from_findings(self.findings, summary)
        return replace(self, **changes)

    def with_findings(self, findings: tuple[Finding, ...] | list[Finding]) -> Review:
        """Return an updated in-progress snapshot; terminal reviews cannot be rewritten."""
        if self.status in {ReviewStatus.COMPLETED, ReviewStatus.FAILED}:
            raise InvalidReviewTransition("Cannot change findings on a terminal review")
        frozen_findings = tuple(findings)
        summary = ReviewSummary.from_findings(frozen_findings, self.summary.text)
        return replace(self, findings=frozen_findings, summary=summary)
