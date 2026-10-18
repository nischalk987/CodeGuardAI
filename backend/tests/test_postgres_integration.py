from fastapi.testclient import TestClient


def test_review_api_against_postgresql(postgres_review_client: TestClient) -> None:
    created = postgres_review_client.post(
        "/api/v1/reviews",
        json={
            "source_code": 'token = "do-not-store-in-logs"\n',
            "file_path": "src/security.py",
        },
    )

    assert created.status_code == 201
    review = created.json()
    fetched = postgres_review_client.get(f"/api/v1/reviews/{review['review_id']}")
    findings = postgres_review_client.get(
        f"/api/v1/reviews/{review['review_id']}/findings",
        params={"severity": "high", "status": "open", "category": "Security"},
    )
    history = postgres_review_client.get("/api/v1/reviews", params={"limit": 20})

    assert fetched.status_code == 200
    assert fetched.json() == review
    assert findings.status_code == 200
    assert len(findings.json()) == 1
    assert history.status_code == 200
    assert review["review_id"] in {item["review_id"] for item in history.json()}
