# CodeGuard AI — Backend

FastAPI starter API for CodeGuard AI.

## Requirements
- Python 3.11 or newer
- pip

## Run locally
From this folder:

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
# Optional: copy the backend-only settings template (it contains no provider credentials):
# Windows PowerShell: Copy-Item .env.example .env
# macOS/Linux: cp .env.example .env
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

## Endpoints
- `GET /health` — health check.
- `GET /api/v1/reviews/demo` — one sample review.
- `GET /api/v1/reviews` — list sample review(s).

## Tests
Run `pytest` and `ruff check app tests` after installing the dev extras.

## Configuration

The API uses Pydantic Settings. Environment variables override the optional `.env` file in the backend working directory.

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `CodeGuard AI API` | FastAPI application title |
| `ENVIRONMENT` | `development` | One of `development`, `test`, or `production` |
| `LOG_LEVEL` | `INFO` | Standard logging level |
| `FRONTEND_ORIGIN` | none | One allowed frontend origin; kept for compatibility |
| `CORS_ORIGINS` | local Vite origins in development | JSON array of allowed origins |

For production, set `FRONTEND_ORIGIN` or `CORS_ORIGINS` explicitly. The API emits JSON logs and redacts common credential fields and token-shaped message values. Error responses use `{"error": {"code", "message", "request_id"}}`; internal exception details are logged with the request ID and are not returned to callers. No provider credentials are loaded by this application foundation.

## Current status
The API returns static sample data. It does not scan repositories, call Groq, persist reviews, authenticate users, or connect to GitHub yet.
