"""Groq infrastructure adapter for the provider-independent AIReviewer interface."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from groq import APIConnectionError, APITimeoutError, AsyncGroq, RateLimitError
from app.ai.exceptions import (
    AIReviewerNotConfigured,
    AIReviewerProviderError,
    AIReviewerRateLimited,
    AIReviewerTimeout,
)
from app.ai.schemas import RESPONSE_JSON_SCHEMA
from app.core.config import Settings
from app.infrastructure.ai.structured_reviewer import StructuredOutputAIReviewer, prompt_messages

logger = logging.getLogger(__name__)
_TRANSIENT_STATUS_CODES = {500, 502, 503, 504}

Sleeper = Callable[[float], Awaitable[None]]


class GroqAIReviewer(StructuredOutputAIReviewer):
    """Review a single bounded source file through Groq without exposing provider errors."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        super().__init__(settings)
        self._sleeper = sleeper
        if client is None:
            if settings.groq_api_key is None:
                raise AIReviewerNotConfigured()
            client = AsyncGroq(
                api_key=settings.groq_api_key.get_secret_value(),
                timeout=settings.groq_timeout_seconds,
                max_retries=0,
            )
        self._client = client

    async def _request_completion(self, prompt_data: str) -> Any:
        attempts = self._settings.groq_max_retries + 1
        for attempt in range(attempts):
            try:
                return await self._client.chat.completions.create(
                    model=self._settings.groq_model,
                    messages=prompt_messages(prompt_data),
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "code_review_findings",
                            "strict": True,
                            "schema": RESPONSE_JSON_SCHEMA,
                        },
                    },
                )
            except Exception as exc:
                status_code = _status_code(exc)
                if status_code == 429 or isinstance(exc, RateLimitError):
                    logger.warning("AI reviewer provider rate limited request")
                    raise AIReviewerRateLimited() from None
                if _is_timeout(exc):
                    if attempt + 1 < attempts:
                        await self._sleeper(min(0.25 * 2**attempt, 1.0))
                        continue
                    logger.warning("AI reviewer provider request timed out")
                    raise AIReviewerTimeout() from None
                if (status_code in _TRANSIENT_STATUS_CODES or _is_connection_error(exc)) and attempt + 1 < attempts:
                    await self._sleeper(min(0.25 * 2**attempt, 1.0))
                    continue
                logger.warning(
                    "AI reviewer provider request failed",
                    extra={"error_type": type(exc).__name__},
                )
                raise AIReviewerProviderError() from None
        raise AIReviewerProviderError() from None


def _status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def _is_timeout(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, asyncio.TimeoutError, APITimeoutError))


def _is_connection_error(exc: Exception) -> bool:
    return isinstance(exc, APIConnectionError)
