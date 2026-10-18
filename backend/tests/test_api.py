from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app, create_app

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


def test_health_response_contains_request_id_header() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_cors_allows_configured_origin_and_rejects_unconfigured_origin() -> None:
    configured_app = create_app(
        Settings(_env_file=None, environment="test", cors_origins=["https://web.example"])
    )
    test_client = TestClient(configured_app)

    allowed = test_client.options(
        "/api/v1/reviews/demo",
        headers={
            "Origin": "https://web.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    rejected = test_client.options(
        "/api/v1/reviews/demo",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://web.example"
    assert "access-control-allow-origin" not in rejected.headers


def test_http_and_validation_errors_use_consistent_safe_shape() -> None:
    test_app = create_app(Settings(_env_file=None, environment="test"))

    @test_app.get("/test-validation")
    def validation_probe(value: int):
        return {"value": value}

    test_client = TestClient(test_app)
    missing = test_client.get("/does-not-exist")
    invalid = test_client.get("/test-validation", params={"value": "not-a-number"})

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "http_error"
    assert missing.json()["error"]["message"] == "Resource not found"
    assert missing.json()["error"]["request_id"]
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert invalid.json()["error"]["message"] == "Request validation failed"
    assert invalid.json()["error"]["request_id"]


def test_unhandled_errors_do_not_expose_exception_details() -> None:
    test_app = create_app(Settings(_env_file=None, environment="test"))

    @test_app.get("/test-failure")
    def failure_probe():
        raise RuntimeError("password=do-not-leak")

    response = TestClient(test_app, raise_server_exceptions=False).get("/test-failure")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert response.json()["error"]["message"] == "Internal server error"
    assert "do-not-leak" not in response.text


def test_demo_summary_counts_match_findings() -> None:
    response = client.get("/api/v1/reviews/demo")
    assert response.status_code == 200
    payload = response.json()
    for severity in ("critical", "high", "medium", "low"):
        assert payload["summary"][severity] == sum(
            finding["severity"] == severity for finding in payload["findings"]
        )
    assert payload["summary"]["total_findings"] == len(payload["findings"])
