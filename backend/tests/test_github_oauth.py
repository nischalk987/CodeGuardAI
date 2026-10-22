import base64
import os

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.api.v1.auth import _issue_token
from app.core.config import Settings
from app.infrastructure.persistence.database import get_session
from app.infrastructure.persistence.models import UserRow
from app.main import create_app
from datetime import datetime, timezone


def _setup(client_factory, monkeypatch):
    key=Fernet.generate_key().decode()
    monkeypatch.setenv("AUTH_SECRET_KEY","a-test-signing-secret-that-is-at-least-32-characters")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID","test-client")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET","test-secret")
    monkeypatch.setenv("GITHUB_OAUTH_REDIRECT_URI","http://localhost:8000/api/v1/github/oauth/callback")
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY",key)
    monkeypatch.setenv("FRONTEND_ORIGIN","http://localhost:5173")

    app=create_app(Settings(_env_file=None,environment="test"))
    def override_session():
        with client_factory["db"]() as session:
            yield session
    app.dependency_overrides[get_session]=override_session
    with client_factory["db"]() as session:
        user=UserRow(id="user-github-test",email="github-test@example.test",display_name="GitHub Test",
                     password_hash="not-used",created_at=datetime.now(timezone.utc))
        session.add(user)
        session.commit()
        token=_issue_token(user)
    return TestClient(app),token,key


def test_github_oauth_start_requires_signed_in_user(review_client, monkeypatch):
    # The fixture is authenticated; verify that OAuth credentials and a valid session are needed.
    from app.main import create_app
    app=create_app(Settings(_env_file=None,environment="test"))
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        response=client.get("/api/v1/github/oauth/start")
    assert response.status_code == 401


def test_repository_browsing_requires_connection(review_client, monkeypatch):
    response=review_client.get("/api/v1/github/oauth/repositories")
    assert response.status_code == 401


def test_github_status_reports_disconnected_for_signed_in_user(migrated_database, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.v1.auth import _issue_token
    from app.core.config import Settings
    from app.infrastructure.persistence.database import get_session
    from app.infrastructure.persistence.models import UserRow
    from app.main import create_app
    from datetime import datetime, timezone

    monkeypatch.setenv("AUTH_SECRET_KEY","a-test-signing-secret-that-is-at-least-32-characters")
    app=create_app(Settings(_env_file=None,environment="test"))
    def override_session():
        with migrated_database() as session:
            yield session
    app.dependency_overrides[get_session]=override_session
    with migrated_database() as session:
        user=UserRow(id="user-status-test",email="status-test@example.test",display_name="Status Test",
                     password_hash="unused",created_at=datetime.now(timezone.utc))
        session.add(user);session.commit()
        token=_issue_token(user)
    with TestClient(app) as client:
        response=client.get("/api/v1/github/oauth/status",headers={"Authorization":f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"connected":False,"login":None}


def test_file_picker_rejects_without_github_connection(review_client):
    response=review_client.get("/api/v1/github/oauth/repositories/octo/repo/branches")
    assert response.status_code == 401
