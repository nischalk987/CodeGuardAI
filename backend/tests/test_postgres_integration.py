from fastapi.testclient import TestClient


def test_review_api_against_postgresql(postgres_review_client: TestClient) -> None:
    payload = {
        "source_code": 'token = "do-not-store-in-logs"\n',
        "file_path": "src/security.py",
    }
    created = postgres_review_client.post(
        "/api/v1/reviews",
        json=payload,
    )

    assert created.status_code == 202
    review = created.json()
    from app.application.reviews import ReviewService
    from app.infrastructure.persistence.repository import SqlAlchemyReviewRepository
    from app.schemas import ReviewCreateRequest

    with postgres_review_client.app.state.review_session_factory() as session:
        ReviewService(SqlAlchemyReviewRepository(session)).execute_queued(
            review["review_id"], ReviewCreateRequest.model_validate(payload)
        )
    fetched = postgres_review_client.get(f"/api/v1/reviews/{review['review_id']}")
    findings = postgres_review_client.get(
        f"/api/v1/reviews/{review['review_id']}/findings",
        params={"severity": "high", "status": "open", "category": "Security"},
    )
    history = postgres_review_client.get("/api/v1/reviews", params={"limit": 20})

    assert fetched.status_code == 200
    assert review["status"] == "queued"
    assert fetched.json()["status"] == "completed"
    assert findings.status_code == 200
    assert len(findings.json()) == 1
    assert history.status_code == 200
    assert review["review_id"] in {item["review_id"] for item in history.json()}
