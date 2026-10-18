"""Hugging Face Inference Providers adapter for structured advisory code reviews."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.ai.exceptions import (
    AIReviewerInvalidResponse,
    AIReviewerNotConfigured,
    AIReviewerProviderError,
    AIReviewerRateLimited,
    AIReviewerTimeout,
)
from app.ai.prompts import PROMPT_VERSION
from app.ai.schemas import RESPONSE_JSON_SCHEMA
from app.core.config import Settings
from app.infrastructure.ai.structured_reviewer import StructuredOutputAIReviewer, prompt_messages

logger = logging.getLogger(__name__)
INFERENCE_URL = "https://router.huggingface.co/v1/chat/completions"
_TRANSIENT_STATUS_CODES = {500, 502, 503, 504}
Sleeper = Callable[[float], Awaitable[None]]


class HuggingFaceAIReviewer(StructuredOutputAIReviewer):
    """Review one bounded source file through Hugging Face Inference Providers."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        super().__init__(settings)
        if settings.hf_token is None:
            raise AIReviewerNotConfigured()
        self._sleeper = sleeper
        self._model = settings.hf_model
        self._max_retries = settings.hf_max_retries
        if client is None:
            client = httpx.AsyncClient(
                timeout=settings.hf_timeout_seconds,
                headers={"Authorization": f"Bearer {settings.hf_token.get_secret_value()}"},
            )
        self._client = client

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool after a CLI review completes."""
        close = getattr(self._client, "aclose", None)
        if close is not None:
            await close()

    async def _request_completion(self, prompt_data: str) -> Any:
        request_body = {
            "model": self._model,
            "messages": prompt_messages(prompt_data),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "code_review_findings",
                    "strict": True,
                    "schema": RESPONSE_JSON_SCHEMA,
                },
            },
        }
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(INFERENCE_URL, json=request_body)
                response.raise_for_status()
                try:
                    return response.json()
                except (json.JSONDecodeError, ValueError, TypeError):
                    logger.warning(
                        "AI reviewer provider returned invalid JSON",
                        extra={"provider": "huggingface", "prompt_version": PROMPT_VERSION},
                    )
                    raise AIReviewerInvalidResponse() from None
            except httpx.TimeoutException:
                if attempt + 1 < self._max_retries + 1:
                    await self._sleeper(min(0.25 * 2**attempt, 1.0))
                    continue
                logger.warning("AI reviewer provider request timed out", extra={"provider": "huggingface"})
                raise AIReviewerTimeout() from None
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code == 429:
                    logger.warning("AI reviewer provider rate limited request", extra={"provider": "huggingface"})
                    raise AIReviewerRateLimited() from None
                if status_code in _TRANSIENT_STATUS_CODES and attempt + 1 < self._max_retries + 1:
                    await self._sleeper(min(0.25 * 2**attempt, 1.0))
                    continue
                logger.warning(
                    "AI reviewer provider request failed",
                    extra={"provider": "huggingface", "status_code": status_code},
                )
                raise AIReviewerProviderError() from None
            except httpx.TransportError as exc:
                if attempt + 1 < self._max_retries + 1:
                    await self._sleeper(min(0.25 * 2**attempt, 1.0))
                    continue
                logger.warning(
                    "AI reviewer provider request failed",
                    extra={"provider": "huggingface", "error_type": type(exc).__name__},
                )
                raise AIReviewerProviderError() from None
        raise AIReviewerProviderError() from None
