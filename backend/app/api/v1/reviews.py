from collections import defaultdict, deque
import hashlib
import json
import logging
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.reviews import ReviewNotFound, ReviewService, risk_score
from app.domain import Finding, Review as ReviewEntity
from app.infrastructure.persistence.database import get_session
from app.infrastructure.persistence.models import ReviewRow, UserRow
from app.api.v1.auth import optional_current_user
from app.infrastructure.persistence.repository import SqlAlchemyReviewRepository
from app.jobs.worker import execute_review
from app.schemas import Finding as FindingResponse
from app.schemas import Review, ReviewCreateRequest, ReviewSummary

router = APIRouter(prefix="/reviews", tags=["reviews"])
logger = logging.getLogger(__name__)

_CREATE_LIMIT = 20
_CREATE_WINDOW_SECONDS = 60
_request_times: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()

# Illustrative sample data, not findings from a real scan.
DEMO_REVIEW = {
    "review_id": "demo-8f31a",
    "repository": "acme/payments-api",
    "branch": "feature/payment-retry",
    "status": "completed",
    "risk_score": 72,
    "summary": {"critical": 1, "high": 2, "medium": 1, "low": 1, "total_findings": 5},
    "findings": [
        {
            "id": "CG-001", "severity": "critical", "category": "Security",
            "file_path": "src/auth/session.py", "line": 84,
            "title": "Session token may be exposed in logs",
            "message": "A token-like value is included in a debug log statement.",
            "explanation": "If this path runs in production, log aggregation could retain session credentials and make them accessible to people who should not have access.",
            "suggested_fix": "Log a request or session identifier instead. Never write the raw token to logs.",
            "source": "static", "confidence": 98,
        },
        {
            "id": "CG-002", "severity": "high", "category": "Reliability",
            "file_path": "src/payments/retry.ts", "line": 42,
            "title": "Retry loop has no upper bound",
            "message": "A failed payment request can be retried without a maximum attempt count.",
            "explanation": "Persistent upstream failures may cause repeated requests, unnecessary cost, and a backlog of work.",
            "suggested_fix": "Set a maximum attempt count and use exponential backoff with jitter.",
            "source": "ai", "confidence": 89,
        },
        {
            "id": "CG-003", "severity": "high", "category": "Security",
            "file_path": "src/api/webhook.py", "line": 117,
            "title": "Webhook signature verification is missing",
            "message": "The handler appears to process a webhook payload before validating its signature.",
            "explanation": "An unauthenticated sender may be able to submit forged events. Confirm the full request path before treating this as a verified vulnerability.",
            "suggested_fix": "Verify the provider signature against the raw request body before processing the event.",
            "source": "ai", "confidence": 83,
        },
        {
            "id": "CG-004", "severity": "medium", "category": "Performance",
            "file_path": "src/reports/query.py", "line": 29,
            "title": "Potential repeated database query",
            "message": "The loop appears to fetch related records separately for each report row.",
            "explanation": "This may create an N+1 query pattern as the report grows.",
            "suggested_fix": "Consider eager loading or a batched query, then compare query counts with a test fixture.",
            "source": "ai", "confidence": 76,
        },
        {
            "id": "CG-005", "severity": "low", "category": "Maintainability",
            "file_path": "src/config.py", "line": 16,
            "title": "Use a named constant for the timeout",
            "message": "The timeout value is embedded directly in the request call.",
            "explanation": "A named configuration value is easier to tune consistently across environments.",
            "suggested_fix": "Move the timeout into validated application configuration.",
            "source": "static", "confidence": 94,
        },
    ],
}


@router.get("/demo", response_model=Review, summary="Get labelled sample review")
def get_demo_review() -> Review:
    """Return static sample data for UI development; no repository is scanned."""
    return Review.model_validate(DEMO_REVIEW)


@router.get("", response_model=list[Review], summary="List persisted reviews")
def list_reviews(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    user: UserRow | None = Depends(optional_current_user),
    session: Session = Depends(get_session),
) -> list[Review]:
    """List only reviews owned by the current account (or legacy unowned reviews)."""
    statement = select(ReviewRow.id).where(
        ReviewRow.owner_user_id == (user.id if user else None)
    ).order_by(ReviewRow.created_at.desc(), ReviewRow.id.desc()).offset(offset).limit(limit)
    ids = session.scalars(statement).all()
    service = ReviewService(SqlAlchemyReviewRepository(session))
    result = []
    for review_id in ids:
        try:
            result.append(_to_response(service.get(review_id)))
        except ReviewNotFound:
            continue
    return result


@router.post("", response_model=Review, status_code=202, summary="Queue a bounded code review")
def create_review(
    payload: ReviewCreateRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=255)] = None,
    user: UserRow | None = Depends(optional_current_user),
    session: Session = Depends(get_session),
) -> Review:
    """Queue bounded deterministic checks; authenticated reviews are scoped to their owner."""
    _enforce_create_rate(request)
    service = ReviewService(SqlAlchemyReviewRepository(session))
    repository = SqlAlchemyReviewRepository(session)
    request_hash = _request_hash(payload)
    if idempotency_key is not None:
        _validate_idempotency_key(idempotency_key)
        previous = repository.find_idempotent(idempotency_key)
        if previous is not None:
            previous_hash, previous_review = previous
            if previous_hash != request_hash:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used for a different review request",
                )
            response.status_code = (
                202
                if previous_review.status.value in {"queued", "running"}
                else 200
            )
            return _to_response(previous_review)

    correlation_id = str(uuid4())
    queued_review = service.create_queued_record(payload, correlation_id=correlation_id)
    try:
        repository.create_queued(
            queued_review,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        if user is not None:
            owned_row = session.get(ReviewRow, queued_review.id)
            if owned_row is not None:
                owned_row.owner_user_id = user.id
                session.commit()
    except IntegrityError:
        session.rollback()
        if idempotency_key is None:
            raise
        previous = repository.find_idempotent(idempotency_key)
        if previous is None:
            raise
        previous_hash, previous_review = previous
        if previous_hash != request_hash:
            raise HTTPException(status_code=409, detail="Idempotency-Key conflicts with an existing request") from None
        response.status_code = 202 if previous_review.status.value in {"queued", "running"} else 200
        return _to_response(previous_review)

    try:
        enqueue_review_task(queued_review.id, payload.model_dump(mode="json"), correlation_id)
    except Exception as exc:
        failed = queued_review.fail(reason="The review queue is temporarily unavailable. Please retry.")
        repository.save(failed)
        logger.error(
            "Review queue submission failed",
            extra={"review_id": queued_review.id, "correlation_id": correlation_id, "error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=503, detail="Review queue is temporarily unavailable") from None
    logger.info(
        "Review queued",
        extra={"review_id": queued_review.id, "correlation_id": correlation_id},
    )
    return _to_response(queued_review)


@router.get("/{review_id}/findings", response_model=list[FindingResponse])
def get_review_findings(
    review_id: str,
    severity: Literal["critical", "high", "medium", "low"] | None = None,
    category: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    status: Literal["open", "accepted", "dismissed", "fixed"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    user: UserRow | None = Depends(optional_current_user),
    session: Session = Depends(get_session),
) -> list[FindingResponse]:
    _assert_review_owner(session, review_id, user)
    service = ReviewService(SqlAlchemyReviewRepository(session))
    try:
        findings = service.findings(
            review_id,
            severity=severity,
            category=category,
            status=status,
            limit=limit,
            offset=offset,
        )
    except ReviewNotFound:
        raise HTTPException(status_code=404, detail="Review not found") from None
    return [_finding_response(item) for item in findings]


@router.get("/{review_id}", response_model=Review, summary="Retrieve a persisted review")
def get_review(
    review_id: str,
    user: UserRow | None = Depends(optional_current_user),
    session: Session = Depends(get_session),
) -> Review:
    _assert_review_owner(session, review_id, user)
    service = ReviewService(SqlAlchemyReviewRepository(session))
    try:
        return _to_response(service.get(review_id))
    except ReviewNotFound:
        raise HTTPException(status_code=404, detail="Review not found") from None


def _assert_review_owner(session: Session, review_id: str, user: UserRow | None) -> None:
    row = session.get(ReviewRow, review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Review not found")
    expected_owner = user.id if user is not None else None
    if row.owner_user_id != expected_owner:
        raise HTTPException(status_code=404, detail="Review not found")


def _finding_response(item: Finding) -> FindingResponse:
    rule_title = (item.rule_id.rsplit(".", 1)[-1]).replace("_", " ").title()
    return FindingResponse(
        id=item.id,
        severity=item.severity.value,
        category=item.category,
        file_path=item.file_path,
        line=item.start_line,
        title=rule_title,
        message=item.message,
        explanation=item.message,
        suggested_fix=item.suggested_fix or "Review this finding and decide on a fix manually.",
        source=item.source.value,
        confidence=item.confidence,
        status=item.status.value,
        rule_id=item.rule_id,
        end_line=item.end_line,
        evidence=item.evidence,
        analyzer_name=item.analyzer_name,
        analyzer_version=item.analyzer_version,
        certainty=item.certainty.value,
    )


def _to_response(review: ReviewEntity) -> Review:
    findings = [_finding_response(item) for item in review.findings]
    return Review(
        review_id=review.id,
        repository=review.repository or "local",
        branch=review.ref or "local",
        status=review.status.value,
        risk_score=risk_score(review.findings),
        summary=ReviewSummary(
            critical=review.summary.critical,
            high=review.summary.high,
            medium=review.summary.medium,
            low=review.summary.low,
            total_findings=review.summary.total_findings,
        ),
        findings=findings,
        correlation_id=review.correlation_id,
        failure_reason=review.failure_reason,
    )


def _request_hash(payload: ReviewCreateRequest) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def enqueue_review_task(review_id: str, request_data: dict[str, str], correlation_id: str) -> None:
    """Dispatch with a redacted task representation so source never appears in task logs."""
    execute_review.apply_async(
        args=[review_id, request_data, correlation_id],
        argsrepr=f"({review_id!r}, '<review payload redacted>', {correlation_id!r})",
    )


def _validate_idempotency_key(value: str) -> None:
    if not value or len(value) > 255 or any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise HTTPException(status_code=422, detail="Idempotency-Key must contain 1–255 visible ASCII characters")


def _enforce_create_rate(request: Request) -> None:
    # Rely only on the direct client address; proxy-provided forwarding headers are untrusted.
    client = request.client.host if request.client else "unknown"
    current = monotonic()
    with _rate_lock:
        for address, entries in list(_request_times.items()):
            while entries and current - entries[0] >= _CREATE_WINDOW_SECONDS:
                entries.popleft()
            if not entries:
                _request_times.pop(address, None)
        if len(_request_times) >= 10_000 and client not in _request_times:
            raise HTTPException(status_code=429, detail="Review request rate limit exceeded")
        timestamps = _request_times[client]
        if len(timestamps) >= _CREATE_LIMIT:
            raise HTTPException(status_code=429, detail="Review request rate limit exceeded")
        timestamps.append(current)


def clear_rate_limit_state() -> None:
    """Clear process-local limiter state in isolated tests."""
    with _rate_lock:
        _request_times.clear()
