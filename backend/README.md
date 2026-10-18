# CodeGuard AI — Backend

FastAPI starter API for CodeGuard AI.

## Requirements
- Python 3.11 or newer
- pip
- PostgreSQL (Neon is supported) for persisted review history

## Run locally
From this folder:

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
# Copy .env.example to .env and set DATABASE_URL privately for persistence.
# Windows PowerShell: Copy-Item .env.example .env
# macOS/Linux: cp .env.example .env
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

## Endpoints
- `GET /health` — health check.
- `GET /api/v1/reviews/demo` — one sample review.
- `POST /api/v1/reviews` — queue a bounded source snippet and return HTTP 202 with its review ID.
- `GET /api/v1/reviews/{review_id}` — retrieve a persisted review.
- `GET /api/v1/reviews?limit=20&offset=0` — paginated review history.
- `GET /api/v1/reviews/{review_id}/findings` — filter findings by severity, category, and status.

The demo endpoint and its response shape are unchanged. Persisted review creation runs only the
local deterministic analyzer. Source is not executed, uploaded to an AI provider, or stored in the
database. The bounded job payload is sent to the configured Redis broker for the worker. Finding
evidence is redacted before persistence. Poll `GET /api/v1/reviews/{review_id}` for queued, running,
completed, or failed status.

Review requests may include an `Idempotency-Key` header (1–255 visible ASCII characters). Reusing
the same key with the same normalized JSON request returns the original review without enqueueing a
second job. Reusing a key with different content returns HTTP 409. Keys are unique across this
application database; clients should generate a new random key for each intentional review.

Run the API and worker as separate processes. Start Redis and set `REDIS_URL` privately in
`backend/.env` (default: `redis://localhost:6379/0`). From `backend/`:

```bash
# Terminal 1: API
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2: Celery worker
celery -A app.jobs.queue:celery_app worker --loglevel=INFO --queues=reviews --pool=solo
```

Transient provider and database errors retry at most three times with exponential backoff capped at
30 seconds. Input/validation failures are not retried. Failed reviews expose only a safe generic
reason and a correlation ID. Task representations redact the review payload; logs include review
and correlation IDs but not source code or provider credentials. Redis carries the bounded source
payload while a job is pending, so use an authenticated, private Redis service for deployments.

## Tests
Run `pytest` and `ruff check app tests` after installing the dev extras.

## Local CLI scanning

The `codeguard` command is installed with the backend package. Its default analyzer runs a
small, deterministic set of local checks for likely hard-coded credentials, dynamic execution,
shell-enabled subprocess calls, and disabled TLS verification. These checks are evidence-based
patterns, not a complete security audit. They read supported source files as data and never
execute repository code. The CLI does not invoke AI review or upload source files unless the
explicit `--ai-review` flag is supplied for one source file.

The built-in analyzer supports `.py`, `.js`, `.jsx`, `.ts`, and `.tsx`, skips unsupported files
when scanning a directory, and reports an error for an explicitly selected unsupported file. It
scans at most 10,000 files and reads at most 1 MB from each file.

```bash
# From backend/ after installing the package
codeguard scan ../frontend/src
codeguard scan ../backend/app --format json
codeguard scan . --fail-on high
codeguard scan . --ignore .venv --ignore node_modules
```

AI review requires an explicit opt-in, a configured credential for the selected `AI_PROVIDER`,
and a single source file. Immediately before the request, the CLI discloses the provider; no
directory or neighboring files are sent. AI findings remain advisory hypotheses.

```bash
codeguard scan src/module.py --ai-review
```

Exit codes are stable for scripts and CI: `0` means the scan completed without a finding at the
selected threshold, `1` means at least one finding met `--fail-on`, and `2` means scanning could
not complete (invalid path, missing analyzer, timeout, or malformed output). `--fail-on` accepts
`none`, `critical`, `high`, `medium`, or `low`; `none` is the default. Text output includes the
file, line, severity, rule ID, message, and analyzer provenance. JSON output uses schema version
`1.0`, includes the shared domain Finding fields and analyzer/version provenance, and groups
duplicates without dropping their individual findings.

The JSON envelope has `schema_version`, `scan`, `summary`, and `finding_groups`. Each group's
`findings` array contains complete shared Finding records (`id`, `rule_id`, `source`, analyzer
name/version, severity, category, message, file path, inclusive line range, confidence, certainty,
original evidence, and optional suggested fix). Group members retain distinct rule IDs and
provenance; `duplicate_count` counts additional members beyond the first.

### Optional Semgrep

Semgrep is optional. Install it with `python -m pip install -e ".[dev,semgrep]"`, then select it:

```bash
codeguard scan . --analyzer semgrep --fail-on high
# Run built-in checks and Semgrep together; duplicate rules are grouped with both provenances.
codeguard scan . --analyzer all --format json
```

The CLI uses `semgrep scan`, not `semgrep ci` or a platform upload command. It disables Semgrep
metrics, runs one worker, caps individual target size, and enforces a wall-clock timeout. The
default `--semgrep-config auto` may download rule definitions from Semgrep's registry; it does
not send source files. Use `--semgrep-config /path/to/rules.yml` for a local rules file. Source is
processed on the local machine and no repository code is executed. See Semgrep's
[local CLI scan documentation](https://semgrep.dev/docs/category/local-and-cli-scans).

Static and AI findings use the same domain schema while retaining their `source`, rule, and
analyzer provenance. Suggested fixes are informational only and are never applied.

## Configuration

The API uses Pydantic Settings. Environment variables override the optional `.env` file in the backend working directory. Copy `backend/.env.example` for local development; credential values are intentionally blank. Put deployment variables in backend-only hosting settings, never frontend build variables.

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `CodeGuard AI API` | FastAPI application title |
| `ENVIRONMENT` | `development` | One of `development`, `test`, or `production` |
| `LOG_LEVEL` | `INFO` | Standard logging level |
| `FRONTEND_ORIGIN` | none | One allowed frontend origin; kept for compatibility |
| `CORS_ORIGINS` | local Vite origins in development | JSON array of allowed origins |
| `DATABASE_URL` | none | Backend-only PostgreSQL connection URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker URL for background reviews |
| `AI_PROVIDER` | `groq` | Optional AI reviewer provider: `groq` or `huggingface` |
| `GROQ_API_KEY` | none | Optional backend-only Groq credential |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Groq model supporting JSON Schema structured output |
| `GROQ_TIMEOUT_SECONDS` | `20` | Per-request SDK timeout, from 0 (exclusive) to 120 seconds |
| `GROQ_MAX_RETRIES` | `2` | Bounded retries for timeouts, connection errors, and transient 5xx errors (0–3) |
| `HF_TOKEN` | none | Optional backend-only Hugging Face Inference Providers token |
| `HF_MODEL` | `openai/gpt-oss-20b` | Hugging Face Inference Providers model ID |
| `HF_TIMEOUT_SECONDS` | `30` | Per-request timeout, from 0 (exclusive) to 120 seconds |
| `HF_MAX_RETRIES` | `2` | Bounded retries for timeouts, connection errors, and transient 5xx errors (0–3) |
| `AI_REVIEW_MAX_INPUT_BYTES` | `40000` | Maximum UTF-8 bytes sent for a single source file |
| `GITHUB_APP_ID` | none | Optional GitHub App ID used by the backend worker |
| `GITHUB_PRIVATE_KEY_PATH` | none | Path to the private GitHub App PEM file; never commit the file |
| `GITHUB_WEBHOOK_SECRET` | none | Secret used to verify GitHub webhook signatures |
| `GITHUB_API_BASE_URL` | `https://api.github.com` | HTTPS API base URL; override for GitHub Enterprise |
| `GITHUB_MAX_DIFF_BYTES` | `100000` | Maximum aggregate PR patch bytes fetched for a review |
| `GITHUB_MAX_FILES` | `50` | Maximum changed files fetched per PR |

For production, set `FRONTEND_ORIGIN` or `CORS_ORIGINS` explicitly. The API emits JSON logs and redacts common credential fields and token-shaped message values. Error responses use `{"error": {"code", "message", "request_id"}}`; internal exception details are logged with the request ID and are not returned to callers. Provider credentials are Pydantic `SecretStr` values, are never logged, and are not included in responses. Keep real local `.env` files out of version control.

### Database setup and migrations

Set `DATABASE_URL` in the private `backend/.env` file. Use the database provider's TLS-enabled
PostgreSQL URL. Never place credentials in source, command-line arguments, frontend settings, or
committed files. Plain `postgresql://` URLs are adapted to SQLAlchemy's `psycopg` driver. API
connections and statements use bounded timeouts.

Before migrating a non-disposable database, verify the selected database and schema with a
read-only connection check. From `backend/`, apply the additive migration and confirm the current
revision:

```bash
alembic upgrade head
alembic current
```

The migrations create the `reviews`, `findings`, and `alembic_version` tables and add nullable
correlation, failure, and idempotency columns plus an idempotency index. They do not rewrite or
delete existing records. Destructive downgrades are disabled; make future schema changes with
forward migrations. Do not point integration tests at production.

PostgreSQL integration tests use `CODEGUARD_TEST_DATABASE_URL`, which must point to a disposable
test database. Each test creates a random schema, applies the migrations there, and removes only
that schema. Regular endpoint tests run the same migrations against a fresh isolated SQLite DB.

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

The `/reviews/demo` route remains illustrative and does not scan a repository. Persisted review
routes scan bounded snippets with local deterministic checks; they do not call Groq or claim AI
analysis.

## Advisory AI reviewer

`app.ai.AIReviewer` is a provider-independent async interface. Groq remains the default; setting
`AI_PROVIDER=huggingface` selects `app.infrastructure.ai.HuggingFaceAIReviewer` through Hugging Face
Inference Providers. Both adapters share the structured-output validation pipeline and return
validated `app.domain.Finding` entities. Each accepts one repository-relative source file per call.
The adapter enforces the configured UTF-8 input limit,
requests strict JSON Schema output, validates that output with Pydantic, checks line ranges and
source evidence, and rejects references to another file. The versioned prompt treats code and
comments as untrusted data. Findings are always marked as AI hypotheses; suggested fixes are
descriptive text and are never executed or applied.

To enable Groq, set `GROQ_API_KEY` in a private backend `.env` file or backend process environment.
Groq remains the default when `AI_PROVIDER` is omitted. To use Hugging Face, set
`AI_PROVIDER=huggingface` and set `HF_TOKEN` to a fine-grained token allowed to call Inference
Providers. Set `HF_MODEL` to a model listed in Hugging Face's [Inference Providers catalog](https://huggingface.co/inference/models?model=openai%2Fgpt-oss-20b);
the default `openai/gpt-oss-20b` is listed with live providers and structured-output support. Groq's
default `openai/gpt-oss-20b` is listed as active and supports JSON Schema output in [Groq's model
catalog](https://console.groq.com/docs/models) and [structured output documentation](https://console.groq.com/docs/structured-outputs).
Availability, schema support, provider routing, account permissions, and free-tier quotas may vary
over time or by account. Both adapters use configurable timeouts and capped retries; timeouts,
network failures, and transient server errors retry within the configured bound, while rate limits
fail without retry. Provider response details are not returned to callers. Malformed model output
is rejected without repair attempts.

The CLI can invoke the configured adapter only when `--ai-review` is explicitly passed for one
source file. It displays a provider-specific upload disclosure before the request, tags results
with provider/model provenance, and does not change the static sample-review endpoints or demo
dashboard. For deployments, set `AI_PROVIDER`, the selected provider's model, and its token as
backend service variables/secrets. Never put either token in frontend hosting variables or a
checked-in `.env` file.

## Current status
The sample API endpoints remain available. Persisted review endpoints use PostgreSQL when
`DATABASE_URL` and the additive Alembic migrations are configured. Review creation returns a
queued job ID and a separate Celery worker updates its persisted lifecycle; Redis is the job broker.
The backend also includes a local CLI, optional Semgrep analyzer, and explicit single-file AI
review option for Groq or Hugging Face Inference Providers. Authentication and GitHub integration
remain future work.

GitHub pull-request intake is optional and requires a separately installed GitHub App.

### GitHub pull-request reviews

Issue #8 uses a GitHub App installation model so repository access is granted by an installation
instead of exposing a user token in the browser. No OAuth token or callback is sent to the frontend.
The signed webhook's delivery UUID, event name, action, installation ID, repository, pull-request
number, and head commit are validated before a review is queued. HMAC-SHA256 signatures are
verified against the raw body with constant-time comparison. Database uniqueness on delivery IDs
and repository, pull request, and head SHA makes repeated deliveries idempotent. Webhook bodies are
size-bounded and requests are acknowledged only after review and delivery mappings are committed.

For local setup, create a GitHub App with only **Pull requests: Read-only** and **Contents:
Read-only** repository permissions, and subscribe to **Pull request** events. Set the App ID,
private-key path, and webhook secret in a private `backend/.env`; keep the PEM file outside the
repository. Configure the webhook URL as `http://localhost:8000/api/v1/github/webhook` using a
local webhook relay, or use the signed fixture tests. Health checks and the existing review routes
work without GitHub credentials; production credentials are not required by the test suite.

Run the API and Celery worker as described above. Missing permissions, API rate limits, and
oversized diffs produce safe failed review states without leaking provider responses or tokens.
The worker fetches PR file patches through the GitHub API, caps file count and total patch bytes,
and runs only existing deterministic checks on added lines in supported source files. It does not
post comments, block merges, execute source code, or call an AI provider. Findings use the shared
advisory domain model and existing review API.
