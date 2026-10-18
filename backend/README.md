# CodeGuard AI — Backend

FastAPI starter API for CodeGuard AI.

## Requirements
- Python 3.11 or newer
- pip

## Run locally
From this folder:

\`\`\`bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
\`\`\`

API docs: http://127.0.0.1:8000/docs

## Endpoints
- \`GET /health\` — health check.
- \`GET /api/v1/reviews/demo\` — one sample review.
- \`GET /api/v1/reviews\` — list sample review(s).

## Tests
Run \`pytest\` after installing the dev extras.

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

## Current status
The API returns static sample data. It does not scan repositories, call Groq, persist reviews, authenticate users, or connect to GitHub yet.
