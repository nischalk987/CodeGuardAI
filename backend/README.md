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
| `GROQ_API_KEY` | none | Optional backend-only Groq credential |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Groq model supporting JSON Schema structured output |
| `GROQ_TIMEOUT_SECONDS` | `20` | Per-request SDK timeout, from 0 (exclusive) to 120 seconds |
| `GROQ_MAX_RETRIES` | `2` | Bounded retries for timeouts, connection errors, and transient 5xx errors (0–3) |
| `AI_REVIEW_MAX_INPUT_BYTES` | `40000` | Maximum UTF-8 bytes sent for a single source file |

For production, set `FRONTEND_ORIGIN` or `CORS_ORIGINS` explicitly. The API emits JSON logs and redacts common credential fields and token-shaped message values. Error responses use `{"error": {"code", "message", "request_id"}}`; internal exception details are logged with the request ID and are not returned to callers. The Groq key is a Pydantic `SecretStr`, is never logged, and is not included in responses. Keep real local `.env` files out of version control.

## Review domain

`app.domain` contains framework-independent `Review` and `Finding` entities. The package uses
standard-library dataclasses and enums and does not import FastAPI, a database layer, or an AI
provider. API request/response schemas remain in `app.schemas`; the sample-review endpoints keep
their existing response shape.

Reviews are immutable snapshots. Lifecycle methods return new snapshots and permit only
`queued → running → completed`, with `failed` allowed from `queued` or `running`. Failed and
completed reviews are terminal; findings cannot be replaced once a review is terminal. To correct
a completed result, retain it as history and create a new review rather than rewriting it.

Finding IDs are deterministic from the rule ID, provenance, repository-relative path, and line
range. Repeated construction of the same finding identity therefore produces the same ID; message
wording and confidence changes do not change that identity. Findings preserve provenance
(`static` or `ai`) separately from certainty (`confirmed` or `hypothesis`). AI findings default to
hypotheses and static findings default to confirmed evidence; callers can set certainty explicitly
when the evidence warrants it. Finding confidence is an integer percentage from 0 through 100,
and line ranges are one-based and inclusive.

The domain entities are not currently used to alter or persist the illustrative `/reviews` sample.
The endpoint remains a static demo and is not evidence of an actual repository scan.

## Advisory AI reviewer

`app.ai.AIReviewer` is a provider-independent async interface. `app.infrastructure.ai.GroqAIReviewer`
implements it using the Groq SDK and returns validated `app.domain.Finding` entities. It accepts one
repository-relative source file per call. The adapter enforces the configured UTF-8 input limit,
requests strict JSON Schema output, validates that output with Pydantic, checks line ranges and
source evidence, and rejects references to another file. The versioned prompt treats code and
comments as untrusted data. Findings are always marked as AI hypotheses; suggested fixes are
descriptive text and are never executed or applied.

To enable the adapter locally, set `GROQ_API_KEY` in a private backend `.env` file or in the
backend process environment. The key is optional for running the existing demo API. Model IDs are
configurable because supported models can change. The adapter requires a model with Groq JSON
Schema structured output support. Free-tier request and token quotas depend on the account and
selected model, can change, and may cause rate-limit or quota errors; check [Groq's current rate
limits](https://console.groq.com/docs/rate-limits). Rate limits fail safely without an automatic
retry, while timeouts, network failures, and transient server errors use the configured bounded
retry count. Malformed model output is rejected without repair attempts.

This adapter is a backend application component; it does not change or replace the static sample
review endpoints, and this issue does not wire it into the demo dashboard.

## Current status
The sample API endpoints return static sample data. The backend includes an optional, programmatic
Groq AI reviewer adapter, but it does not persist reviews, authenticate users, or connect to
GitHub yet.
