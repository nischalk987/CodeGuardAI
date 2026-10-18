"""Bounded GitHub App API client. Tokens and provider responses are never logged."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any

import httpx
import jwt
import json

from app.core.config import Settings


class GitHubClientError(RuntimeError):
    """Safe base error for GitHub API failures."""


class GitHubPermissionError(GitHubClientError):
    pass


class GitHubRateLimitError(GitHubClientError):
    pass


class GitHubDiffLimitError(GitHubClientError):
    pass


@dataclass(frozen=True, slots=True)
class ChangedFile:
    path: str
    additions: tuple[str, ...]
    line_numbers: tuple[int, ...]


class GitHubAppClient:
    """Authenticate as an installed GitHub App and fetch a bounded PR file diff."""

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=3.0))

    def close(self) -> None:
        self._client.close()

    def installation_token(self, installation_id: int) -> str:
        if not self.settings.github_app_id or not self.settings.github_private_key_path:
            raise GitHubClientError("GitHub App credentials are not configured")
        try:
            private_key = Path(self.settings.github_private_key_path).read_text(encoding="utf-8")
            now = int(time())
            app_jwt = jwt.encode(
                {"iat": now - 30, "exp": now + 8 * 60, "iss": self.settings.github_app_id},
                private_key,
                algorithm="RS256",
            )
        except (OSError, ValueError, TypeError, jwt.PyJWTError):
            raise GitHubClientError("GitHub App credentials could not be loaded") from None
        url = f"{self.settings.github_api_base_url}/app/installations/{installation_id}/access_tokens"
        try:
            response = self._client.post(
                url,
                headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28"},
            )
        except httpx.HTTPError:
            raise GitHubClientError("GitHub authentication service is unavailable") from None
        self._check_response(response)
        token = response.json().get("token")
        if not isinstance(token, str) or not token:
            raise GitHubClientError("GitHub did not issue an installation token")
        return token

    def fetch_pull_request_files(
        self, repository: str, pull_request_number: int, installation_id: int,
        expected_sha: str | None = None,
    ) -> tuple[ChangedFile, ...]:
        token = self.installation_token(installation_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        metadata_url = (
            f"{self.settings.github_api_base_url}/repos/{repository}/pulls/{pull_request_number}"
        )
        try:
            metadata_response = self._client.get(metadata_url, headers=headers)
        except httpx.HTTPError:
            raise GitHubClientError("GitHub pull-request service is unavailable") from None
        self._check_response(metadata_response)
        try:
            metadata = metadata_response.json()
            current_sha = metadata["head"]["sha"]
        except (ValueError, TypeError, KeyError):
            raise GitHubClientError("GitHub returned invalid pull-request metadata") from None
        if expected_sha and current_sha != expected_sha:
            raise GitHubClientError("Pull request changed after the webhook was delivered")

        url = (
            f"{self.settings.github_api_base_url}/repos/{repository}/pulls/"
            f"{pull_request_number}/files?per_page={min(self.settings.github_max_files, 100)}"
        )
        try:
            with self._client.stream("GET", url, headers=headers) as response:
                self._check_response(response)
                link_header = response.headers.get("Link", "")
                raw_body = bytearray()
                maximum_response = self.settings.github_max_diff_bytes + 64_000
                for chunk in response.iter_bytes():
                    raw_body.extend(chunk)
                    if len(raw_body) > maximum_response:
                        raise GitHubDiffLimitError(
                            "Pull request diff response exceeds the configured size limit"
                        )
        except httpx.HTTPError:
            raise GitHubClientError("GitHub pull-request service is unavailable") from None
        if 'rel="next"' in link_header:
            raise GitHubDiffLimitError("Pull request exceeds the configured changed-file limit")
        try:
            payload: Any = json.loads(raw_body)
        except ValueError:
            raise GitHubClientError("GitHub returned an invalid pull-request response") from None
        if not isinstance(payload, list) or len(payload) > self.settings.github_max_files:
            raise GitHubDiffLimitError("Pull request exceeds the configured changed-file limit")
        total = 0
        files: list[ChangedFile] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            path, patch = item.get("filename"), item.get("patch", "")
            if not isinstance(path, str) or not isinstance(patch, str):
                continue
            total += len(patch.encode("utf-8"))
            if total > self.settings.github_max_diff_bytes:
                raise GitHubDiffLimitError("Pull request diff exceeds the configured size limit")
            additions, lines = _added_lines(patch)
            files.append(ChangedFile(path=path, additions=additions, line_numbers=lines))
        return tuple(files)

    @staticmethod
    def _check_response(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise GitHubRateLimitError("GitHub API rate limit was reached")
        if response.status_code == 403:
            if response.headers.get("X-RateLimit-Remaining") == "0" or response.headers.get("Retry-After"):
                raise GitHubRateLimitError("GitHub API rate limit was reached")
            raise GitHubPermissionError("GitHub App lacks permission to read this pull request")
        if response.status_code in {401, 404}:
            raise GitHubPermissionError("GitHub App cannot access this pull request")
        if response.status_code >= 400:
            raise GitHubClientError("GitHub API request failed")
        if response.status_code >= 300:
            raise GitHubClientError("Unexpected GitHub API response")


def _added_lines(patch: str) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """Extract changed source and its new-file line numbers from a unified diff."""
    import re

    added: list[str] = []
    line_numbers: list[int] = []
    current = 0
    for line in patch.splitlines():
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,\d+)?", line)
            current = int(match.group(1)) if match else 0
        elif line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+"):
            added.append(line[1:])
            line_numbers.append(current)
            current += 1
        elif line.startswith(" "):
            current += 1
        elif line.startswith("-"):
            continue
    return tuple(added), tuple(line_numbers)
