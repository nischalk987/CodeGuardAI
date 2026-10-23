from fastapi.testclient import TestClient

from app.api.v1.reviews import clear_rate_limit_state
from app.core.config import Settings
from app.main import create_app


def test_create_and_retrieve_review_persists_across_app_instances(
    review_client: TestClient,
    migrated_database,
    run_queued_review,
) -> None:
    payload = {
        "source_code": 'password = "not-a-placeholder"\n',
        "file_path": "src/auth.py",
        "repository": "example/payments",
        "branch": "feature/session",
    }
    created = review_client.post(
        "/api/v1/reviews",
        json=payload,
    )
    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    run_queued_review(migrated_database, created.json()["review_id"], payload)
    result = review_client.get(f"/api/v1/reviews/{created.json()['review_id']}").json()
    assert result["status"] == "completed"
    assert result["findings"][0]["file_path"] == "src/auth.py"
    assert result["findings"][0]["line"] == 1
    assert result["findings"][0]["severity"] in {"critical", "high", "medium", "low"}
    assert result["findings"][0]["rule_id"] == "CG.SEC.HARDCODED_CREDENTIAL"
    assert "not-a-placeholder" not in result["findings"][0]["evidence"]
    assert result["summary"]["total_findings"] == 1

    second_app = create_app(Settings(_env_file=None, environment="test"))

    def session_override():
        with migrated_database() as session:
            yield session

    from app.infrastructure.persistence.database import get_session

    second_app.dependency_overrides[get_session] = session_override
    with TestClient(second_app) as restarted_client:
        retrieved = restarted_client.get(f"/api/v1/reviews/{result['review_id']}")
        history = restarted_client.get("/api/v1/reviews", params={"limit": 1, "offset": 0})

    assert retrieved.status_code == 200
    assert retrieved.json() == result
    assert history.status_code == 200
    assert [item["review_id"] for item in history.json()] == [result["review_id"]]


def test_review_history_paginates_and_unknown_ids_return_404(review_client: TestClient) -> None:
    ids = []
    for index in range(3):
        response = review_client.post(
            "/api/v1/reviews", json={"source_code": f"value_{index} = {index}\n"}
        )
        assert response.status_code == 202
        ids.append(response.json()["review_id"])

    page = review_client.get("/api/v1/reviews", params={"limit": 2, "offset": 1})
    assert page.status_code == 200
    assert len(page.json()) == 2
    assert page.json()[0]["review_id"] == ids[1]

    missing = review_client.get("/api/v1/reviews/rev_does_not_exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "http_error"


def test_findings_can_be_filtered_by_severity_category_and_status(
    review_client: TestClient, migrated_database, run_queued_review
) -> None:
    payload = {
        "source_code": 'password = "long-private-value"\nverify = False\n',
        "file_path": "src/security.py",
    }
    created = review_client.post(
        "/api/v1/reviews",
        json=payload,
    )
    review_id = created.json()["review_id"]
    run_queued_review(migrated_database, review_id, payload)

    response = review_client.get(
        f"/api/v1/reviews/{review_id}/findings",
        params={"severity": "high", "category": "security", "status": "open"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert all(item["severity"] == "high" for item in response.json())
    assert all(item["status"] == "open" for item in response.json())


def test_review_input_is_bounded_and_rejects_unsafe_paths(review_client: TestClient) -> None:
    oversized = review_client.post("/api/v1/reviews", json={"source_code": "é" * 20_001})
    traversal = review_client.post(
        "/api/v1/reviews", json={"source_code": "x=1", "file_path": "../secret.py"}
    )
    unsupported = review_client.post(
        "/api/v1/reviews", json={"source_code": "x=1", "file_path": "notes.txt"}
    )
    oversized_body = review_client.post(
        "/api/v1/reviews", content='{"source_code":"' + ("x" * 50_000) + '"}'
    )

    assert oversized.status_code == 422
    assert traversal.status_code == 422
    assert unsupported.status_code == 422
    assert oversized_body.status_code == 413
    assert oversized_body.json()["error"]["code"] == "request_too_large"
    assert all(item.json()["error"]["code"] == "validation_error" for item in (oversized, traversal))


def test_review_creation_is_rate_limited(review_client: TestClient) -> None:
    clear_rate_limit_state()
    for index in range(20):
        response = review_client.post(
            "/api/v1/reviews", json={"source_code": f"value = {index}\n"}
        )
        assert response.status_code == 202

    limited = review_client.post("/api/v1/reviews", json={"source_code": "value = 21\n"})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "http_error"
    clear_rate_limit_state()


def test_idempotency_key_reuses_one_job_and_rejects_different_payload(
    review_client: TestClient, monkeypatch
) -> None:
    from app.api.v1 import reviews as routes

    calls = []
    monkeypatch.setattr(routes, "enqueue_review_task", lambda *args: calls.append(args))
    headers = {"Idempotency-Key": "test-review-001"}
    payload = {"source_code": "safe_value = 1\n", "file_path": "src/sample.py"}

    first = review_client.post("/api/v1/reviews", json=payload, headers=headers)
    repeated = review_client.post("/api/v1/reviews", json=payload, headers=headers)
    conflict = review_client.post(
        "/api/v1/reviews",
        json={"source_code": "different = 2\n", "file_path": "src/sample.py"},
        headers=headers,
    )

    assert first.status_code == repeated.status_code == 202
    assert first.json()["review_id"] == repeated.json()["review_id"]
    assert first.json()["status"] == "queued"
    assert len(calls) == 1
    assert conflict.status_code == 409


def test_history_pagination_limits_are_validated(review_client: TestClient) -> None:
    too_many = review_client.get("/api/v1/reviews", params={"limit": 101})
    negative = review_client.get("/api/v1/reviews", params={"offset": -1})

    assert too_many.status_code == 422
    assert negative.status_code == 422


def test_queue_failure_is_persisted_and_visible_in_review_detail(
    review_client: TestClient, monkeypatch
) -> None:
    from app.api.v1 import reviews as routes

    def fail_enqueue(*_args):
        raise RuntimeError("queue is offline")

    monkeypatch.setattr(routes, "enqueue_review_task", fail_enqueue)
    created = review_client.post(
        "/api/v1/reviews",
        json={
            "source_code": 'password = "local-only-secret"\n',
            "file_path": "src/auth.py",
            "repository": "example/payments",
            "branch": "feature/retry",
        },
    )
    assert created.status_code == 503

    history = review_client.get("/api/v1/reviews")
    assert history.status_code == 200
    assert len(history.json()) == 1
    failed = history.json()[0]
    assert failed["status"] == "failed"
    assert failed["failure_reason"] == "The review queue is temporarily unavailable. Please retry."

    detail = review_client.get(f"/api/v1/reviews/{failed['review_id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "failed"
    assert detail.json()["repository"] == "example/payments"
    assert detail.json()["branch"] == "feature/retry"



def test_optional_ai_failure_preserves_deterministic_review(
    review_client: TestClient, migrated_database, monkeypatch
) -> None:
    from app.ai.exceptions import AIReviewerNotConfigured
    from app.application import reviews as review_application
    from app.application.reviews import ReviewService
    from app.infrastructure.persistence.repository import SqlAlchemyReviewRepository
    from app.schemas import ReviewCreateRequest

    def no_provider(_settings):
        raise AIReviewerNotConfigured()

    monkeypatch.setattr(review_application, "create_ai_reviewer", no_provider)
    payload = {
        "source_code": 'password = "private-value-example"\\n',
        "file_path": "src/auth.py",
        "repository": "example/payments",
        "branch": "feature/ai",
        "ai_review": True,
    }
    created = review_client.post("/api/v1/reviews", json=payload)
    assert created.status_code == 202
    assert created.json()["ai_review_requested"] is True
    assert created.json()["ai_review_status"] == "pending"

    with migrated_database() as session:
        result = ReviewService(SqlAlchemyReviewRepository(session)).execute_queued(
            created.json()["review_id"], ReviewCreateRequest.model_validate(payload)
        )
    assert result.status.value == "completed"
    assert result.ai_review_status == "unavailable"
    assert result.ai_review_message
    assert any(finding.source.value == "static" for finding in result.findings)
