# CodeGuard AI — 2–3 minute demo script

**Before the call:** run `docker compose up --build` and open the dashboard, API docs, and GitHub Actions page. No AI credentials are needed for the dashboard demo.

## 0:00–0:25 — Set context
“CodeGuard AI is an early-stage code-review MVP. It pairs deterministic rules with optional AI hypotheses. The dashboard currently shows labelled sample findings; it does not claim to scan code live.”

## 0:25–0:55 — Dashboard
Open http://localhost:5173. Show severity counts, search/filter controls, and one finding's details. Demonstrate local accept/dismiss triage. Call out that findings are illustrative.

## 0:55–1:20 — API
Open http://localhost:8000/docs and show `GET /api/v1/reviews/demo` and `GET /health`. Point out the demo endpoint label and explain that real API operations require backend services to be configured.

## 1:20–1:55 — Local CLI
From the repo root, run:

```bash
cd backend
python -m pip install -e ".[dev]"
python -m codeguard scan tests/fixtures/static_sample.py --format json
```

Explain that deterministic checks run locally; source is not uploaded unless the explicit single-file `--ai-review` option is used.

## 1:55–2:25 — Engineering quality
Show Actions: backend tests, frontend typecheck/build/tests, dependency audits, secret scanning, and adversarial prompt-injection tests. Mention bounded inputs/retries and strict model output validation.

## 2:25–2:55 — Honest roadmap
“Still unfinished: dashboard live scanning and complete GitHub PR diff review/inline annotations. AI is advisory, prompt wording is not a sandbox, and all suggested fixes require human review.”
