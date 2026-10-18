"""Small ASGI request-size guard for the public snippet-review endpoint."""

from collections import deque
from typing import Any
from uuid import uuid4

from starlette.responses import JSONResponse


class ReviewBodyLimitMiddleware:
    """Buffer only bounded review request bodies before FastAPI parses JSON."""

    def __init__(self, app: Any, max_bytes: int = 50_000) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/api/v1/reviews"
        ):
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        content_length = next(
            (value for name, value in scope.get("headers", []) if name.lower() == b"content-length"),
            None,
        )
        if content_length is not None:
            try:
                too_large = int(content_length) > self.max_bytes
            except ValueError:
                too_large = True
            if too_large:
                await _too_large(scope, receive, send, request_id, self.max_bytes)
                return

        messages: deque[dict[str, Any]] = deque()
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            messages.append(message)
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await _too_large(scope, receive, send, request_id, self.max_bytes)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive():
            if messages:
                return messages.popleft()
            return await receive()

        await self.app(scope, replay_receive, send)


async def _too_large(scope, receive, send, request_id: str, max_bytes: int) -> None:
    response = JSONResponse(
        status_code=413,
        content={
            "error": {
                "code": "request_too_large",
                "message": f"Review request body exceeds the {max_bytes} byte limit",
                "request_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )
    await response(scope, receive, send)
