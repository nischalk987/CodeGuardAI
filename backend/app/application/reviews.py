"""Review use cases independent of FastAPI and concrete database adapters."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from app.ai.exceptions import AIReviewerError, AIReviewerNotConfigured
from app.core.config import Settings
from app.infrastructure.ai.factory import create_ai_reviewer
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


logger = logging.getLogger(__name__)


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
            ai_review_requested=request.ai_review,
            ai_review_status="pending" if request.ai_review else "disabled",
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

        ai_status = "disabled"
        ai_message = None
        if request.ai_review:
            try:
                reviewer = create_ai_reviewer(Settings())
                ai_findings = asyncio.run(
                    reviewer.review(file_path=request.file_path, source_code=request.source_code)
                )
                # Model findings remain labelled hypotheses alongside deterministic findings.
                findings = (*findings, *ai_findings)
                ai_status = "completed"
                ai_message = "AI findings are suggestions/hypotheses. Verify them independently."
            except AIReviewerNotConfigured:
                ai_status = "unavailable"
                ai_message = "AI review is not configured. Deterministic findings are still available."
            except AIReviewerError as exc:
                ai_status = "failed"
                ai_message = f"{exc.safe_message}. Deterministic findings are still available."
                logger.warning("Optional AI review failed", extra={"error_type": type(exc).__name__})
            except Exception as exc:
                # A provider outage must never discard or fail deterministic findings.
                ai_status = "failed"
                ai_message = "AI review failed. Deterministic findings are still available."
                logger.warning("Optional AI review failed", extra={"error_type": type(exc).__name__})

        review = replace(
            review,
            ai_review_requested=request.ai_review,
            ai_review_status=ai_status,
            ai_review_message=ai_message,
        )
        if ai_status == "completed":
            summary_text = "Completed deterministic checks with optional advisory AI suggestions."
        elif not request.ai_review:
            summary_text = "Completed deterministic checks. AI review was not requested."
        elif ai_status == "unavailable":
            summary_text = "Completed deterministic checks. Optional AI reviewer is unavailable."
        else:
            summary_text = "Completed deterministic checks. Optional AI review failed."
        review = review.with_findings(findings).complete(summary=summary_text)
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
