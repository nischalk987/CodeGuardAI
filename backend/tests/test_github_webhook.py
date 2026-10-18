import hashlib
import hmac
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.v1.github import verify_webhook_signature
from app.core.config import Settings
from app.infrastructure.persistence.database import get_session
from app.infrastructure.persistence.models import GitHubPullRequestReviewRow, ReviewRow
from app.main import create_app
from sqlalchemy import select


SECRET = "local-test-webhook-secret"


def _signature(payload: bytes) -> str:
    digest = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _event() -> bytes:
    return json.dumps(
        {
            "action": "opened",
            "number": 7,
            "repository": {"full_name": "acme/payments"},
            "installation": {"id": 1234},
            "pull_request": {"head": {"sha": "a" * 40}},
        }
    ).encode()


def _client(database, monkeypatch):
    app = create_app(Settings(_env_file=None, environment="test", github_webhook_secret=SECRET))

    def override_session():
        with database() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    enqueued = []
    monkeypatch.setattr(
        "app.api.v1.github.enqueue_github_review", lambda *args: enqueued.append(args)
    )
    return TestClient(app), enqueued


def test_signature_uses_sha256_and_rejects_malformed_values():
    body = b"payload"
    signature = _signature(body)
    assert verify_webhook_signature(SECRET, body, signature)
    assert not verify_webhook_signature(SECRET, body, "sha256=" + "0" * 64)
    assert not verify_webhook_signature(SECRET, body, "sha1=bad")
    assert not verify_webhook_signature(SECRET, body, None)


def test_webhook_creates_one_review_and_duplicate_pr_delivery_reuses_it(
    migrated_database, monkeypatch
):
    client, enqueued = _client(migrated_database, monkeypatch)
    body = _event()
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": str(uuid4()),
        "X-Hub-Signature-256": _signature(body),
    }
    first = client.post("/api/v1/github/webhook", content=body, headers=headers)
    second = client.post(
        "/api/v1/github/webhook", content=body, headers=headers
    )
    third = client.post(
        "/api/v1/github/webhook", content=body,
        headers={**headers, "X-GitHub-Delivery": str(uuid4())},
    )

    assert first.status_code == 202
    assert second.status_code == 200
    assert third.status_code == 200
    assert first.json()["review_id"] == second.json()["review_id"]
    assert first.json()["review_id"] == third.json()["review_id"]
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert third.json()["duplicate"] is True
    assert len(enqueued) == 1
    with migrated_database() as session:
        assert len(session.scalars(select(ReviewRow)).all()) == 1
        mapping = session.scalars(select(GitHubPullRequestReviewRow)).one()
        assert mapping.repository == "acme/payments"
        assert mapping.pull_request_number == 7
        assert mapping.commit_sha == "a" * 40


def test_webhook_rejects_bad_signature_and_malformed_delivery_id(migrated_database, monkeypatch):
    client, _ = _client(migrated_database, monkeypatch)
    body = _event()
    bad_signature = client.post(
        "/api/v1/github/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": str(uuid4()),
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
        },
    )
    bad_delivery = client.post(
        "/api/v1/github/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "not-a-uuid",
            "X-Hub-Signature-256": _signature(body),
        },
    )
    assert bad_signature.status_code == 401
    assert bad_delivery.status_code == 400


def test_duplicate_delivery_retries_enqueue_after_initial_queue_failure(
    migrated_database, monkeypatch
):
    client, _ = _client(migrated_database, monkeypatch)
    attempts = []

    def enqueue(*args):
        attempts.append(args)
        if len(attempts) == 1:
            raise RuntimeError("broker unavailable")

    monkeypatch.setattr("app.api.v1.github.enqueue_github_review", enqueue)
    body = _event()
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": str(uuid4()),
        "X-Hub-Signature-256": _signature(body),
    }
    first = client.post("/api/v1/github/webhook", content=body, headers=headers)
    retry = client.post("/api/v1/github/webhook", content=body, headers=headers)
    assert first.status_code == 503
    assert retry.status_code == 200
    assert retry.json()["duplicate"] is True
    assert len(attempts) == 2


def test_review_diff_parsing_preserves_added_line_numbers():
    from app.infrastructure.github.client import _added_lines

    lines, locations = _added_lines("@@ -4,2 +4,3 @@\n context\n-old\n+password = 'secret'\n+next = 1\n")
    assert lines == ("password = 'secret'", "next = 1")
    assert locations == (5, 6)


def test_github_api_client_uses_mocked_metadata_and_bounded_file_response():
    import httpx

    from app.core.config import Settings
    from app.infrastructure.github.client import GitHubAppClient

    def respond(request):
        if request.url.path.endswith("/files"):
            return httpx.Response(
                200,
                json=[{"filename": "src/auth.py", "patch": "@@ -0,0 +1,1 @@\n+safe = True"}],
                request=request,
            )
        return httpx.Response(200, json={"head": {"sha": "b" * 40}}, request=request)

    api = httpx.Client(transport=httpx.MockTransport(respond))
    github = GitHubAppClient(Settings(_env_file=None, environment="test"), client=api)
    github.installation_token = lambda _installation_id: "mock-installation-token"
    files = github.fetch_pull_request_files("acme/payments", 7, 1234, expected_sha="b" * 40)
    github.close()
    assert files[0].path == "src/auth.py"
    assert files[0].additions == ("safe = True",)
    assert files[0].line_numbers == (1,)


def test_github_api_client_handles_rate_limit_permissions_and_oversized_diff():
    import httpx
    import pytest

    from app.core.config import Settings
    from app.infrastructure.github.client import (
        GitHubAppClient,
        GitHubDiffLimitError,
        GitHubPermissionError,
        GitHubRateLimitError,
    )

    with pytest.raises(GitHubRateLimitError):
        GitHubAppClient._check_response(
            httpx.Response(403, headers={"X-RateLimit-Remaining": "0"})
        )
    with pytest.raises(GitHubPermissionError):
        GitHubAppClient._check_response(httpx.Response(403))

    def respond(request):
        if request.url.path.endswith("/files"):
            patch = "@@ -0,0 +1,1001 @@\n+" + ("x" * 1001)
            return httpx.Response(200, json=[{"filename": "src/a.py", "patch": patch}], request=request)
        return httpx.Response(200, json={"head": {"sha": "c" * 40}}, request=request)

    api = httpx.Client(transport=httpx.MockTransport(respond))
    github = GitHubAppClient(
        Settings(_env_file=None, environment="test", github_max_diff_bytes=1000), client=api
    )
    github.installation_token = lambda _installation_id: "mock-installation-token"
    with pytest.raises(GitHubDiffLimitError):
        github.fetch_pull_request_files("acme/payments", 7, 1234, expected_sha="c" * 40)
    github.close()


def test_github_worker_scans_added_lines_and_persists_repository_locations(
    migrated_database, monkeypatch
):
    from datetime import datetime, timezone

    from app.infrastructure.github.client import ChangedFile
    from app.infrastructure.persistence.models import ReviewRow

    engine = migrated_database.kw["bind"]
    with migrated_database() as session:
        now = datetime.now(timezone.utc)
        session.add(
            ReviewRow(
                id="rev_github_worker_test",
                source_type="pull_request",
                repository="acme/payments",
                branch="d" * 40,
                status="queued",
                risk_score=0,
                summary_text="",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    class MockGitHubClient:
        def __init__(self, _settings):
            pass

        def fetch_pull_request_files(self, *_args, **_kwargs):
            return (
                ChangedFile(
                    "src/auth.py",
                    ("password = 'private-value'",),
                    (42,),
                ),
            )

        def close(self):
            pass

    monkeypatch.setattr("app.jobs.github_worker.get_engine", lambda: engine)
    monkeypatch.setattr("app.jobs.github_worker.GitHubAppClient", MockGitHubClient)
    from app.jobs.github_worker import execute_github_review

    result = execute_github_review.run(
        "rev_github_worker_test", "acme/payments", 7, "d" * 40, 1234
    )
    with migrated_database() as session:
        review = session.get(ReviewRow, "rev_github_worker_test")
        assert review is not None
        assert review.status == "completed"
        assert review.findings[0].file_path == "src/auth.py"
        assert review.findings[0].line == 42
    assert result == "completed"
