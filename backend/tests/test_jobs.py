from dataclasses import replace

import pytest
from sqlalchemy.engine import Engine

from app.ai.exceptions import AIReviewerInputError, AIReviewerProviderError
from app.application.reviews import ReviewService
from app.infrastructure.persistence.repository import SqlAlchemyReviewRepository
from app.jobs import worker
from app.api.v1 import reviews as review_routes
from app.schemas import ReviewCreateRequest


def test_queue_task_redacts_source_from_celery_task_representation(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        review_routes.execute_review,
        "apply_async",
        lambda **kwargs: captured.update(kwargs),
    )
    review_routes.enqueue_review_task(
        "rev_redaction",
        {"source_code": "private-token-value", "file_path": "src/token.py"},
        "correlation-redaction",
    )

    assert "private-token-value" not in captured["argsrepr"]
    assert "<review payload redacted>" in captured["argsrepr"]
    assert captured["args"][1]["source_code"] == "private-token-value"


def _queued_review(factory, *, review_id: str = "rev_worker_test") -> tuple[str, Engine]:
    correlation_id = "42eb31bd-6a86-4e26-83af-d22b27e2f02a"
    request = ReviewCreateRequest(source_code="safe = 1\n")
    with factory() as session:
        service = ReviewService(SqlAlchemyReviewRepository(session))
        review = service.create_queued_record(request, correlation_id=correlation_id)
        review = replace(review, id=review_id)
        SqlAlchemyReviewRepository(session).create_queued(
            review, idempotency_key=None, request_hash="a" * 64
        )
    with factory() as session:
        return review_id, session.get_bind()


def test_worker_retries_transient_provider_error_with_bounded_backoff(
    migrated_database, monkeypatch
) -> None:
    review_id, engine = _queued_review(migrated_database)
    monkeypatch.setattr(worker, "get_engine", lambda: engine)

    def transient_failure(service, review_id, _request):
        service._repository.claim_queued(review_id)
        raise AIReviewerProviderError()

    monkeypatch.setattr(ReviewService, "execute_queued", transient_failure)
    retry_values = {}

    class RetryRequested(Exception):
        pass

    def request_retry(*, exc, countdown):
        retry_values.update(error=str(exc), countdown=countdown)
        raise RetryRequested()

    monkeypatch.setattr(worker.execute_review, "retry", request_retry)
    with pytest.raises(RetryRequested):
        worker.execute_review.run(review_id, {"source_code": "private", "file_path": "x.py"}, "corr")

    assert worker.execute_review.max_retries == 3
    assert retry_values == {"error": "Transient review dependency failure", "countdown": 2}
    with migrated_database() as session:
        queued_again = SqlAlchemyReviewRepository(session).get(review_id)
    assert queued_again is not None
    assert queued_again.status.value == "queued"


def test_duplicate_worker_delivery_does_not_reprocess_terminal_review(
    migrated_database, monkeypatch
) -> None:
    review_id, engine = _queued_review(migrated_database)
    monkeypatch.setattr(worker, "get_engine", lambda: engine)

    result = worker.execute_review.run(
        review_id,
        {"source_code": "safe = 1\n", "file_path": "snippet.py", "repository": "local", "branch": "local"},
        "42eb31bd-6a86-4e26-83af-d22b27e2f02a",
    )
    assert result == "completed"

    monkeypatch.setattr(
        ReviewService,
        "execute_queued",
        lambda *_args, **_kwargs: pytest.fail("terminal review must not be reprocessed"),
    )

    duplicate_result = worker.execute_review.run(
        review_id, {"source_code": "safe = 1\n", "file_path": "snippet.py"}, "corr"
    )

    assert duplicate_result == "completed"


def test_worker_does_not_retry_invalid_input_and_persists_safe_failure(
    migrated_database, monkeypatch, caplog
) -> None:
    review_id, engine = _queued_review(migrated_database)
    monkeypatch.setattr(worker, "get_engine", lambda: engine)

    def invalid_input(*_args, **_kwargs):
        raise AIReviewerInputError()

    monkeypatch.setattr(ReviewService, "execute_queued", invalid_input)
    monkeypatch.setattr(worker.execute_review, "retry", lambda **_kwargs: pytest.fail("must not retry"))
    result = worker.execute_review.run(
        review_id,
        {"source_code": "private-token-value", "file_path": "src/sample.py"},
        "42eb31bd-6a86-4e26-83af-d22b27e2f02a",
    )

    assert result == "failed"
    with migrated_database() as session:
        failed = SqlAlchemyReviewRepository(session).get(review_id)
    assert failed is not None
    assert failed.failure_reason == "The review could not be completed. Please try again."
    assert failed.correlation_id == "42eb31bd-6a86-4e26-83af-d22b27e2f02a"
    assert "private-token-value" not in caplog.text
