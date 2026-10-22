from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.v1.auth import _issue_token
from app.core.config import Settings
from app.infrastructure.persistence.database import get_session
from app.infrastructure.persistence.models import UserRow
from app.main import create_app


def _authenticated_client(database, monkeypatch):
    monkeypatch.setenv("AUTH_SECRET_KEY", "a-test-signing-secret-that-is-at-least-32-characters")
    app = create_app(Settings(_env_file=None, environment="test"))

    def override_session():
        with database() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with database() as session:
        user = UserRow(
            id="github-oauth-test-user",
            email="github-oauth-test@example.test",
            display_name="GitHub OAuth Test",
            password_hash="unused-test-hash",
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        session.commit()
        token = _issue_token(user)
    return TestClient(app), token


def test_oauth_start_requires_signed_in_user(migrated_database):
    app = create_app(Settings(_env_file=None, environment="test"))
    with TestClient(app) as client:
        response = client.get("/api/v1/github/oauth/start")
    assert response.status_code == 401


def test_repository_browsing_requires_connection(review_client):
    response = review_client.get("/api/v1/github/oauth/repositories")
    assert response.status_code == 401


def test_status_reports_disconnected_for_signed_in_user(migrated_database, monkeypatch):
    client, token = _authenticated_client(migrated_database, monkeypatch)
    with client:
        response = client.get(
            "/api/v1/github/oauth/status",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    assert response.json() == {"connected": False, "login": None}


def test_file_picker_rejects_without_github_connection(review_client):
    response = review_client.get("/api/v1/github/oauth/repositories/octo/repo/branches")
    assert response.status_code == 401
