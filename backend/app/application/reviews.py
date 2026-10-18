"""Review use cases independent of FastAPI and concrete database adapters."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.analysis import BuiltinAnalyzer
from app.analysis.base import AnalyzerError
from app.core.logging import redact_sensitive_text
from app.domain import (
    Finding,
    Review,
    ReviewSourceType,
    Severity,
)
from app.schemas import ReviewCreateRequest


class ReviewRepository(Protocol):
    def save(self, review: Review) -> None: ...

    def claim_queued(self, review_id: str) -> Review | None: ...

    def get(self, review_id: str) -> Review | None: ...

    def list(self, *, limit: int, offset: int) -> list[Review]: ...

    def findings(
        self,
        review_id: str,
        *,
        severity: str | None,
        category: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[Finding]: ...


class ReviewNotFound(LookupError):
    def __init__(self, review_id: str) -> None:
        self.review_id = review_id
        super().__init__("Review not found")


class ReviewService:
    """Bounded local static review creation and persistent review-history operations."""

    def __init__(self, repository: ReviewRepository) -> None:
        self._repository = repository

    def create_queued_record(
        self, request: ReviewCreateRequest, *, correlation_id: str | None
    ) -> Review:
        """Create a queued review snapshot without scanning source code."""
        now = datetime.now(timezone.utc)
        return Review(
            id=f"rev_{uuid4().hex}",
            source_type=ReviewSourceType.SNIPPET,
            repository=request.repository,
            ref=request.branch,
            created_at=now,
            updated_at=now,
            correlation_id=correlation_id,
        )

    def execute_queued(self, review_id: str, request: ReviewCreateRequest) -> Review:
        """Run the deterministic analyzer for an existing queued review."""
        review = self._repository.claim_queued(review_id)
        if review is None:
            return self.get(review_id)
        suffix = Path(request.file_path).suffix.lower()
        if suffix not in {".py", ".js", ".jsx", ".ts", ".tsx"}:
            failed = review.fail(reason="The submitted file type cannot be scanned.")
            self._repository.save(failed)
            return failed
        try:
            findings = tuple(
                replace(
                    item,
                    file_path=request.file_path,
                    evidence=redact_sensitive_text(item.evidence),
                )
                for item in BuiltinAnalyzer().analyze_source(request.source_code, request.file_path)
            )
        except AnalyzerError:
            failed = review.fail(reason="The submitted snippet could not be scanned.")
            self._repository.save(failed)
            return failed

        review = review.with_findings(findings).complete(
            summary="Completed a local deterministic scan. No AI provider was called."
        )
        self._repository.save(review)
        return review

    def get(self, review_id: str) -> Review:
        review = self._repository.get(review_id)
        if review is None:
            raise ReviewNotFound(review_id)
        return review

    def list(self, *, limit: int, offset: int) -> list[Review]:
        return self._repository.list(limit=limit, offset=offset)

    def findings(
        self,
        review_id: str,
        *,
        severity: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Finding]:
        if self._repository.get(review_id) is None:
            raise ReviewNotFound(review_id)
        return self._repository.findings(
            review_id,
            severity=severity,
            category=category,
            status=status,
            limit=limit,
            offset=offset,
        )


def risk_score(findings: tuple[Finding, ...]) -> int:
    weights = {
        Severity.CRITICAL: 35,
        Severity.HIGH: 20,
        Severity.MEDIUM: 10,
        Severity.LOW: 3,
    }
    return min(100, sum(weights[item.severity] for item in findings))
