import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.reviews import router as reviews_router

app = FastAPI(
    title="CodeGuard AI API",
    description="API foundation for the CodeGuard AI code review platform.",
    version="0.1.0",
)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(reviews_router, prefix="/api/v1")


@app.get("/health", tags=["system"], summary="Health check")
def health_check() -> dict[str, str]:
    """Return a small non-sensitive health payload."""
    return {"status": "ok", "service": "codeguard-ai-api"}


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "CodeGuard AI API", "docs": "/docs"}