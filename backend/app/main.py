import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.reviews import router as reviews_router
from app.api.v1.github import router as github_router
from app.api.v1.auth import router as auth_router
from app.api.v1.workspace import router as workspace_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.request_limits import ReviewBodyLimitMiddleware
from app.infrastructure.persistence.database import DatabaseNotConfigured
from app.schemas import ErrorResponse

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid4()))


def _error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    payload = ErrorResponse(
        error={"code": code, "message": message, "request_id": _request_id(request)}
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    messages = {
        400: "Bad request",
        401: "Authentication required",
        403: "Access denied",
        404: "Resource not found",
        405: "Method not allowed",
        409: "Request conflicts with the current resource state",
        429: "Too many requests",
    }
    message = messages.get(exc.status_code, "Request could not be completed")
    return _error_response(request, exc.status_code, "http_error", message)


async def validation_exception_handler(
    request: Request, _exc: RequestValidationError
) -> JSONResponse:
    return _error_response(request, 422, "validation_error", "Request validation failed")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled API exception",
        extra={"request_id": _request_id(request), "path": request.url.path},
    )
    return _error_response(request, 500, "internal_error", "Internal server error")


async def database_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    # Database exceptions may contain connection context; do not log their text or traceback.
    logger.error(
        "Review database unavailable",
        extra={"request_id": _request_id(request), "error_type": type(exc).__name__},
    )
    return _error_response(
        request, 503, "database_unavailable", "Review storage is temporarily unavailable"
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API using validated settings, with an injectable settings object for tests."""
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    application = FastAPI(
        title=app_settings.app_name,
        description="API foundation for the CodeGuard AI code review platform.",
        version="0.1.0",
    )
    application.state.settings = app_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    )
    application.add_middleware(ReviewBodyLimitMiddleware, max_bytes=50_000)

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):
        # Use a new ID rather than trusting arbitrary caller-supplied text in logs.
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(DatabaseNotConfigured, database_unavailable_handler)
    application.add_exception_handler(SQLAlchemyError, database_unavailable_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)
    application.include_router(reviews_router, prefix="/api/v1")
    application.include_router(github_router, prefix="/api/v1")
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(workspace_router, prefix="/api/v1")

    @application.get("/health", tags=["system"], summary="Health check")
    def health_check() -> dict[str, str]:
        """Return a small non-sensitive health payload."""
        return {"status": "ok", "service": "codeguard-ai-api"}

    @application.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "CodeGuard AI API", "docs": "/docs"}

    return application


app = create_app()
