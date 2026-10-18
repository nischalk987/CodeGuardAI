"""GitHub App PR webhook intake. Webhook credentials never leave the backend."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain import Review, ReviewSourceType
from app.infrastructure.persistence.database import get_session
from app.infrastructure.persistence.models import (
    GitHubDeliveryRow,
    GitHubPullRequestReviewRow,
    ReviewRow,
)
from app.jobs.github_worker import enqueue_github_review

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/github", tags=["github"])
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SHA = re.compile(r"^[0-9a-fA-F]{40,64}$")
_SUPPORTED_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review"}
_WEBHOOK_RATE_LIMIT = 120
_WEBHOOK_WINDOW_SECONDS = 60
_webhook_times: dict[str, deque[float]] = defaultdict(deque)
_webhook_lock = Lock()


def verify_webhook_signature(secret: str, body: bytes, signature: str | None) -> bool:
    """Verify GitHub's SHA-256 webhook signature using a constant-time comparison."""
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    supplied = signature[7:]
    if not re.fullmatch(r"[0-9a-fA-F]{64}", supplied):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied.lower())


@router.post("/webhook", status_code=202, summary="Accept a verified GitHub pull-request event")
async def github_webhook(
    request: Request,
    response: Response,
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict[str, str | bool]:
    settings = request.app.state.settings
    if not _allow_webhook_request(request.client.host if request.client else "unknown"):
        raise HTTPException(status_code=429, detail="GitHub webhook rate limit exceeded")
    secret = settings.github_webhook_secret
    if secret is None:
        raise HTTPException(status_code=503, detail="GitHub webhook integration is not configured")
    body = await request.body()
    if not verify_webhook_signature(secret.get_secret_value(), body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")
    try:
        delivery_id = str(UUID(x_github_delivery or ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook delivery identifier") from None
    if x_github_event != "pull_request":
        return {"accepted": True, "duplicate": False, "message": "Event ignored"}

    try:
        event = json.loads(body)
        action = event.get("action")
        repository = event["repository"]["full_name"]
        number = event["number"]
        commit_sha = event["pull_request"]["head"]["sha"]
        installation_id = event["installation"]["id"]
        if (
            not isinstance(action, str)
            or not isinstance(repository, str)
            or not _REPOSITORY.fullmatch(repository)
            or not isinstance(number, int)
            or isinstance(number, bool)
            or number < 1
            or not isinstance(commit_sha, str)
            or not _SHA.fullmatch(commit_sha)
            or not isinstance(installation_id, int)
            or isinstance(installation_id, bool)
            or installation_id < 1
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(status_code=422, detail="Unsupported or malformed pull-request event") from None
    if action not in _SUPPORTED_ACTIONS:
        return {"accepted": True, "duplicate": False, "message": "Pull-request action ignored"}

    previous_delivery = session.get(GitHubDeliveryRow, delivery_id)
    if previous_delivery:
        response.status_code = 200
        _reenqueue_if_pending(previous_delivery, session)
        return {"accepted": True, "duplicate": True, "review_id": previous_delivery.review_id or ""}

    identity = (repository, number, commit_sha)
    existing = session.get(GitHubPullRequestReviewRow, identity)
    if existing:
        response.status_code = 200
        return {"accepted": True, "duplicate": True, "review_id": existing.review_id}

    now = datetime.now(timezone.utc)
    review = Review(
        id=f"rev_{uuid4().hex}",
        source_type=ReviewSourceType.PULL_REQUEST,
        repository=repository,
        ref=commit_sha,
        created_at=now,
        updated_at=now,
        correlation_id=str(uuid4()),
    )
    request_hash = hashlib.sha256(f"{repository}:{number}:{commit_sha}".encode()).hexdigest()
    session.add(
        ReviewRow(
            id=review.id,
            source_type=review.source_type.value,
            repository=repository,
            branch=commit_sha,
            status=review.status.value,
            risk_score=0,
            summary_text="",
            created_at=now,
            updated_at=now,
            correlation_id=review.correlation_id,
            idempotency_key=f"github:{repository}:{number}:{commit_sha}",
            request_hash=request_hash,
        )
    )
    session.add(
        GitHubPullRequestReviewRow(
            repository=repository,
            pull_request_number=number,
            commit_sha=commit_sha,
            review_id=review.id,
            installation_id=installation_id,
            created_at=now,
        )
    )
    session.add(
        GitHubDeliveryRow(
            delivery_id=delivery_id,
            event_name="pull_request",
            action=action,
            repository=repository,
            pull_request_number=number,
            commit_sha=commit_sha,
            review_id=review.id,
            received_at=now,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # Concurrent redeliveries race on the unique delivery/PR identity keys.
        existing = session.get(GitHubPullRequestReviewRow, identity)
        if existing is None:
            raise HTTPException(status_code=503, detail="GitHub event could not be recorded") from None
        response.status_code = 200
        return {"accepted": True, "duplicate": True, "review_id": existing.review_id}

    try:
        enqueue_github_review(review.id, repository, number, commit_sha, installation_id)
    except Exception as exc:
        logger.error(
            "GitHub review queue submission failed",
            extra={"review_id": review.id, "error_type": type(exc).__name__},
        )
        # GitHub will retry; a duplicate delivery re-enqueues a still-pending review.
        raise HTTPException(status_code=503, detail="Review queue is temporarily unavailable") from None
    delivery = session.get(GitHubDeliveryRow, delivery_id)
    if delivery is not None:
        delivery.enqueue_confirmed = True
        session.commit()
    return {"accepted": True, "duplicate": False, "review_id": review.id}


def _allow_webhook_request(client: str) -> bool:
    now = monotonic()
    with _webhook_lock:
        for address, timestamps in list(_webhook_times.items()):
            while timestamps and now - timestamps[0] >= _WEBHOOK_WINDOW_SECONDS:
                timestamps.popleft()
            if not timestamps:
                _webhook_times.pop(address, None)
        if len(_webhook_times) >= 10_000 and client not in _webhook_times:
            return False
        timestamps = _webhook_times[client]
        if len(timestamps) >= _WEBHOOK_RATE_LIMIT:
            return False
        timestamps.append(now)
        return True


def _reenqueue_if_pending(delivery: GitHubDeliveryRow, session: Session) -> None:
    review_id = delivery.review_id
    if not review_id or delivery.enqueue_confirmed:
        return
    row = session.scalar(select(ReviewRow).where(ReviewRow.id == review_id))
    if row is not None and row.status == "queued":
        mapping = session.scalar(
            select(GitHubPullRequestReviewRow).where(GitHubPullRequestReviewRow.review_id == review_id)
        )
        if mapping is not None:
            enqueue_github_review(
                review_id,
                mapping.repository,
                mapping.pull_request_number,
                mapping.commit_sha,
                mapping.installation_id,
            )
            delivery.enqueue_confirmed = True
            session.commit()
