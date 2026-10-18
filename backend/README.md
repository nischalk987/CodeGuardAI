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
.venv\Scripts\Activate.ps1
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

## Current status
The API returns static sample data. It does not scan repositories, call Groq, persist reviews, authenticate users, or connect to GitHub yet.