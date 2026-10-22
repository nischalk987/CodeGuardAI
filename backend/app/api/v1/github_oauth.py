"""Signed-in GitHub OAuth and bounded repository browsing.

The access token is encrypted at rest in the database and never returned to the
browser. Set GITHUB_TOKEN_ENCRYPTION_KEY to a Fernet key (generated with
cryptography.fernet.Fernet.generate_key()) and OAuth settings in the backend env.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import current_user
from app.infrastructure.persistence.database import get_session
from app.infrastructure.persistence.models import GitHubOAuthConnectionRow, UserRow

router = APIRouter(prefix="/github/oauth", tags=["github-oauth"])
_STATE_TTL = 600
_STATE_COOKIE = "codeguard_github_oauth_state"
_GITHUB_TOKEN_COOKIE = "codeguard_github_connected"
_API_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
_MAX_FILE_BYTES = 40_000


def _oauth_settings() -> tuple[str, str, str, str]:
    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("GITHUB_OAUTH_REDIRECT_URI", "").strip()
    frontend = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").strip().rstrip("/")
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured on the server")
    if not frontend.startswith(("http://localhost", "http://127.0.0.1", "https://")):
        raise HTTPException(status_code=503, detail="Frontend origin is invalid")
    return client_id, client_secret, redirect_uri, frontend


def _fernet() -> Fernet:
    key = os.getenv("GITHUB_TOKEN_ENCRYPTION_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="GitHub token encryption is not configured")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise HTTPException(status_code=503, detail="GitHub token encryption key is invalid") from None


def _state_secret() -> bytes:
    secret = os.getenv("AUTH_SECRET_KEY", "").strip()
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="OAuth state signing is not configured")
    return secret.encode()


def _make_state(user_id: str) -> str:
    payload = f"{int(time.time())}:{user_id}:{secrets.token_urlsafe(24)}"
    sig = hmac.new(_state_secret(), payload.encode(), hashlib.sha256).digest()
    b64 = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
    return b64(payload.encode()) + "." + b64(sig)


def _validate_state(state: str, user_id: str) -> None:
    try:
        encoded, signature = state.split(".", 1)
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        expected = hmac.new(_state_secret(), raw, hashlib.sha256).digest()
        issued_text, state_user_id, nonce = raw.decode().split(":", 2)
        issued = int(issued_text)
        now = int(time.time())
        if (
            not hmac.compare_digest(supplied, expected)
            or state_user_id != user_id
            or not nonce
            or issued > now
            or now - issued > _STATE_TTL
        ):
            raise ValueError
    except (ValueError, TypeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid or expired GitHub authorization state") from None


def _token_for_user(user: UserRow, session: Session) -> str:
    row = session.get(GitHubOAuthConnectionRow, user.id)
    if row is None:
        raise HTTPException(status_code=401, detail="Connect your GitHub account first")
    try:
        return _fernet().decrypt(row.encrypted_access_token.encode()).decode()
    except InvalidToken:
        raise HTTPException(status_code=503, detail="Stored GitHub connection cannot be decrypted; reconnect") from None


async def _github_get(client: httpx.AsyncClient, url: str, token: str, **kwargs) -> httpx.Response:
    try:
        response = await client.get(url, headers={**_API_HEADERS, "Authorization": f"Bearer {token}"}, **kwargs)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="GitHub API is temporarily unavailable") from None
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="GitHub connection expired; reconnect your account")
    if response.status_code == 403:
        if response.headers.get("X-RateLimit-Remaining") == "0":
            raise HTTPException(status_code=429, detail="GitHub API rate limit reached; retry later")
        raise HTTPException(status_code=403, detail="GitHub denied access to this repository or resource")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="GitHub repository, branch, or file was not found or is not accessible")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="GitHub API request failed")
    return response


@router.get("/start")
async def start_oauth(request: Request, user: UserRow = Depends(current_user)) -> Response:
    client_id, _, redirect_uri, _ = _oauth_settings()
    state = _make_state(user.id)
    secure = request.url.scheme == "https"
    response = RedirectResponse(
        "https://github.com/login/oauth/authorize?" + urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "repo read:user",
            "state": state,
        }),
        status_code=303,
    )
    response.set_cookie(_STATE_COOKIE, state, httponly=True, secure=secure, samesite="lax", max_age=_STATE_TTL, path="/api/v1/github/oauth")
    return response


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_session),
) -> Response:
    _, client_secret, redirect_uri, frontend = _oauth_settings()
    if error:
        raise HTTPException(status_code=400, detail="GitHub authorization was denied")
    if not code or not state:
        raise HTTPException(status_code=400, detail="GitHub did not return an authorization code")
    cookie_state = request.cookies.get(_STATE_COOKIE)
    # Resolve the CodeGuard user from the user ID inside the signed, short-lived state.
    try:
        encoded = state.split(".", 1)[0]
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        _, state_user_id, _ = raw.split(":", 2)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid GitHub authorization state") from None
    if not cookie_state or not hmac.compare_digest(cookie_state, state):
        raise HTTPException(status_code=400, detail="GitHub authorization state did not match this browser")
    user = session.get(UserRow, state_user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to CodeGuard before connecting GitHub")
    _validate_state(state, user.id)
    client_id, _, _, _ = _oauth_settings()
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            exchange = await client.post(
                "https://github.com/login/oauth/access_token",
                data={"client_id": client_id, "client_secret": client_secret, "code": code, "redirect_uri": redirect_uri},
                headers={"Accept": "application/json"},
            )
            exchange.raise_for_status()
            payload = exchange.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(status_code=502, detail="GitHub token exchange failed; retry authorization") from None
        token = payload.get("access_token")
        if not isinstance(token, str) or not token or payload.get("error"):
            raise HTTPException(status_code=401, detail="GitHub authorization was not completed")
        profile = await _github_get(client, "https://api.github.com/user", token)
    login = str(profile.json().get("login", ""))[:100]
    if not login:
        raise HTTPException(status_code=502, detail="GitHub did not return an account identity")
    row = session.get(GitHubOAuthConnectionRow, user.id)
    encrypted = _fernet().encrypt(token.encode()).decode()
    if row is None:
        row = GitHubOAuthConnectionRow(
            user_id=user.id,
            github_login=login,
            encrypted_access_token=encrypted,
            connected_at=datetime.now(timezone.utc),
        )
        session.add(row)
    else:
        row.github_login = login
        row.encrypted_access_token = encrypted
        row.connected_at = datetime.now(timezone.utc)
    session.commit()
    response = RedirectResponse(url=frontend + "/workspace?github=connected", status_code=303)
    response.delete_cookie(_STATE_COOKIE, path="/api/v1/github/oauth")
    return response


@router.get("/status")
def connection_status(
    user: UserRow = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    row = session.get(GitHubOAuthConnectionRow, user.id)
    return {"connected": row is not None, "login": row.github_login if row else None}


@router.get("/repositories")
async def list_github_repositories(
    user: UserRow = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    token = _token_for_user(user, session)
    repos: list[dict[str, object]] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for page in range(1, 11):
            response = await _github_get(
                client, "https://api.github.com/user/repos", token,
                params={"per_page": 100, "page": page, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
            )
            batch = response.json()
            if not isinstance(batch, list):
                raise HTTPException(status_code=502, detail="GitHub returned an invalid repository list")
            repos.extend({
                "id": repo["id"], "full_name": repo["full_name"], "private": repo["private"],
                "html_url": repo["html_url"], "default_branch": repo["default_branch"],
                "description": repo.get("description"),
            } for repo in batch if isinstance(repo, dict) and all(
                key in repo for key in ("id", "full_name", "private", "html_url", "default_branch")
            ))
            if len(batch) < 100:
                break
    return repos


@router.get("/repositories/{owner}/{repo}/branches")
async def list_repository_branches(
    owner: str,
    repo: str,
    user: UserRow = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, str]]:
    token = _token_for_user(user, session)
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await _github_get(
            client, f"https://api.github.com/repos/{owner}/{repo}/branches", token,
            params={"per_page": 100},
        )
    result = response.json()
    if not isinstance(result, list):
        raise HTTPException(status_code=502, detail="GitHub returned an invalid branch list")
    return [{"name": item["name"], "commit_sha": item["commit"]["sha"]} for item in result if isinstance(item, dict) and item.get("name") and isinstance(item.get("commit"), dict) and item["commit"].get("sha")]


@router.get("/repositories/{owner}/{repo}/files")
async def list_repository_files(
    owner: str,
    repo: str,
    branch: str = Query(min_length=1, max_length=255),
    user: UserRow = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    token = _token_for_user(user, session)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await _github_get(
            client, f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}",
            token, params={"recursive": "1"},
        )
    result = response.json()
    tree = result.get("tree") if isinstance(result, dict) else None
    if not isinstance(tree, list):
        raise HTTPException(status_code=502, detail="GitHub returned an invalid repository tree")
    files = []
    supported = (".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb", ".swift", ".kt", ".sql", ".sh", ".yaml", ".yml", ".json", ".toml")
    for item in tree:
        path = item.get("path") if isinstance(item, dict) else None
        if item.get("type") == "blob" and isinstance(path, str) and path.lower().endswith(supported):
            files.append({"path": path, "size": item.get("size", 0)})
            if len(files) >= 1000:
                break
    return files


@router.get("/repositories/{owner}/{repo}/file")
async def get_repository_file(
    owner: str,
    repo: str,
    path: str = Query(min_length=1, max_length=500),
    ref: str = Query(min_length=1, max_length=255),
    user: UserRow = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, str | int]:
    token = _token_for_user(user, session)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await _github_get(
            client, f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            token, params={"ref": ref},
        )
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("type") != "file":
        raise HTTPException(status_code=422, detail="Selected GitHub path is not a source file")
    size = payload.get("size", 0)
    if not isinstance(size, int) or size > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Selected file exceeds the 40 KB review limit")
    if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
        raise HTTPException(status_code=422, detail="GitHub did not return a decodable file")
    try:
        raw = base64.b64decode(payload["content"], validate=False)
        content = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="Selected file is not UTF-8 source text") from None
    if len(raw) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Selected file exceeds the 40 KB review limit")
    return {"path": path, "content": content, "size": len(raw)}


@router.post("/disconnect", status_code=204)
def disconnect_github(
    user: UserRow = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    row = session.get(GitHubOAuthConnectionRow, user.id)
    if row is not None:
        session.delete(row)
        session.commit()
    return Response(status_code=204)
