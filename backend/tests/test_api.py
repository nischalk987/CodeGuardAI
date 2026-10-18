from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "codeguard-ai-api"}


def test_demo_review_has_expected_shape() -> None:
    response = client.get("/api/v1/reviews/demo")
    assert response.status_code == 200
    payload = response.json()
    assert payload["review_id"] == "demo-8f31a"
    assert payload["summary"]["total_findings"] == len(payload["findings"]) == 5
    assert payload["findings"][0]["severity"] == "critical"
    assert payload["findings"][0]["source"] == "static"


def test_review_list_returns_sample_review() -> None:
    response = client.get("/api/v1/reviews")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_demo_findings_have_valid_line_and_confidence_ranges() -> None:
    response = client.get("/api/v1/reviews/demo")
    assert response.status_code == 200
    for finding in response.json()["findings"]:
        assert finding["line"] >= 1
        assert 0 <= finding["confidence"] <= 100


def test_demo_summary_counts_match_findings() -> None:
    response = client.get("/api/v1/reviews/demo")
    assert response.status_code == 200
    payload = response.json()
    for severity in ("critical", "high", "medium", "low"):
        assert payload["summary"][severity] == sum(
            finding["severity"] == severity for finding in payload["findings"]
        )
    assert payload["summary"]["total_findings"] == len(payload["findings"])
