"""Review task worker. Source is passed through Redis, never written to logs."""

from __future__ import annotations

import logging

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.ai.exceptions import AIReviewerProviderError, AIReviewerRateLimited, AIReviewerTimeout
from app.application.reviews import ReviewService
from app.core.logging import redact_sensitive_text
from app.domain.enums import ReviewStatus
from app.infrastructure.persistence.database import get_engine
from app.infrastructure.persistence.repository import SqlAlchemyReviewRepository
from app.jobs.queue import celery_app
from app.schemas import ReviewCreateRequest

logger = logging.getLogger(__name__)
_TRANSIENT_ERRORS = (
    AIReviewerProviderError,
    AIReviewerRateLimited,
    AIReviewerTimeout,
    OperationalError,
    TimeoutError,
)
_PUBLIC_FAILURE = "The review could not be completed. Please try again."


@celery_app.task(bind=True, name="codeguard.execute_review", max_retries=3)
def execute_review(
    self,
    review_id: str,
    request_data: dict[str, str],
    correlation_id: str,
):
    """Execute a queued review with bounded exponential retry for transient failures."""
    with Session(get_engine(), expire_on_commit=False) as session:
        repository = SqlAlchemyReviewRepository(session)
        service = ReviewService(repository)
        try:
            review = service.get(review_id)
            if review.status in {ReviewStatus.COMPLETED, ReviewStatus.FAILED}:
                return review.status.value
            result = service.execute_queued(
                review_id, ReviewCreateRequest.model_validate(request_data)
            )
        except _TRANSIENT_ERRORS as exc:
            if self.request.retries < self.max_retries:
                delay = min(2 ** (self.request.retries + 1), 30)
                current = service.get(review_id)
                if current.status is ReviewStatus.RUNNING:
                    repository.save(current.requeue())
                logger.warning(
                    "Review job will retry",
                    extra={"review_id": review_id, "correlation_id": correlation_id},
                )
                raise self.retry(
                    exc=RuntimeError("Transient review dependency failure"),
                    countdown=delay,
                ) from None
            _mark_failed(repository, service, review_id, correlation_id, type(exc).__name__)
            return ReviewStatus.FAILED.value
        except Exception as exc:
            # Never log exception text or traceback: validation/provider exceptions can contain input.
            _mark_failed(repository, service, review_id, correlation_id, type(exc).__name__)
            return ReviewStatus.FAILED.value

        logger.info(
            "Review job finished",
            extra={"review_id": review_id, "correlation_id": correlation_id},
        )
        return result.status.value


def _mark_failed(
    repository: SqlAlchemyReviewRepository,
    service: ReviewService,
    review_id: str,
    correlation_id: str,
    error_type: str,
) -> None:
    review = service.get(review_id)
    if review.status in {ReviewStatus.COMPLETED, ReviewStatus.FAILED}:
        return
    repository.save(review.fail(reason=_PUBLIC_FAILURE))
    logger.error(
        "Review job failed",
        extra={
            "review_id": review_id,
            "correlation_id": correlation_id,
            "error_type": redact_sensitive_text(error_type),
        },
    )
