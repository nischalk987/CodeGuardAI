"""GitHub OAuth authorization and repository discovery.

OAuth credentials are backend-only. GitHub's user token is held in an HttpOnly
cookie for local development; production deployments must use HTTPS and set secure
cookies. Configure GITHUB_OAUTH_CLIENT_ID/SECRET and GITHUB_OAUTH_REDIRECT_URI.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/github/oauth", tags=["github-oauth"])
_STATE_TTL = 600
_COOKIE_NAME = "codeguard_github_token"


def _state_secret() -> bytes:
    secret = os.getenv("AUTH_SECRET_KEY", "").strip()
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="OAuth state signing is not configured")
    return secret.encode()


def _settings() -> tuple[str, str, str]:
    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("GITHUB_OAUTH_REDIRECT_URI", "").strip()
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
    return client_id, client_secret, redirect_uri


def _make_state() -> str:
    payload = f"{int(time.time())}:{secrets.token_urlsafe(24)}"
    sig = hmac.new(_state_secret(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def _validate_state(state: str) -> None:
    try:
        encoded, signature = state.split(".", 1)
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        expected = hmac.new(_state_secret(), payload, hashlib.sha256).digest()
        issued = int(payload.decode().split(":", 1)[0])
        if not hmac.compare_digest(supplied, expected) or issued > int(time.time()) or int(time.time()) - issued > _STATE_TTL:
            raise ValueError
    except (ValueError, TypeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state") from None


@router.get("/start")
async def start_oauth() -> dict[str, str]:
    client_id, _, redirect_uri = _settings()
    state = _make_state()
    url = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "repo read:user",
        "state": state,
    })
    return {"authorization_url": url, "state": state}


@router.get("/callback")
async def oauth_callback(request: Request, code: str, state: str) -> Response:
    client_id, client_secret, redirect_uri = _settings()
    _validate_state(state)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={"client_id": client_id, "client_secret": client_secret,
                      "code": code, "redirect_uri": redirect_uri},
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            payload = token_response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(status_code=502, detail="GitHub token exchange failed") from None
    token = payload.get("access_token")
    if not isinstance(token, str) or not token or payload.get("error"):
        raise HTTPException(status_code=401, detail="GitHub authorization was not completed")
    frontend = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")
    response = RedirectResponse(url=frontend + "/workspace?github=connected", status_code=303)
    response.set_cookie(
        _COOKIE_NAME, token, httponly=True, secure=request.url.scheme == "https",
        samesite="lax", max_age=payload.get("expires_in", 28800), path="/api/v1/github",
    )
    return response


@router.get("/repositories")
async def list_github_repositories(request: Request) -> list[dict[str, object]]:
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Connect your GitHub account first")
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            result = await client.get(
                "https://api.github.com/user/repos",
                params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"},
            )
            if result.status_code == 401:
                raise HTTPException(status_code=401, detail="GitHub connection expired; reconnect")
            result.raise_for_status()
            repos = result.json()
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="Could not fetch GitHub repositories") from None
    return [{
        "id": repo["id"], "full_name": repo["full_name"], "private": repo["private"],
        "html_url": repo["html_url"], "default_branch": repo["default_branch"],
        "description": repo.get("description"),
    } for repo in repos if isinstance(repo, dict) and all(k in repo for k in ("id", "full_name", "private", "html_url", "default_branch"))]


@router.post("/disconnect", status_code=204)
async def disconnect_github() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(_COOKIE_NAME, path="/api/v1/github")
    return response
