# Security Policy

## Scope

CodeGuard AI is an early-stage project. Its security controls and integrations are under active development; do not assume that planned mitigations already exist.

## Reporting a vulnerability

Please do **not** publish exploitable details, API keys, access tokens, private source code, or sensitive personal data in a public issue.

Use GitHub's private vulnerability reporting feature for this repository when available. If private reporting is not enabled, contact the repository owner through a private channel before disclosing details publicly. Include impact, reproduction steps, affected commit/version, and any safe proof of concept.

## Secret handling

- Never commit `.env` files, API tokens, private keys, webhook secrets, or production database credentials.
- Keep real values in an untracked local `.env` file or your deployment secret manager.
- `.env.example` files must contain placeholder values only.
- If a secret is exposed, revoke or rotate it immediately; removing it from the latest commit is not sufficient.
- Do not log credentials, authorization headers, or private source code.

## Automated checks

GitHub Actions runs Python dependency auditing with `pip-audit`, frontend dependency auditing with `npm audit`, and repository secret scanning with Gitleaks. Findings must be reviewed and remediated before merging. Dependency audits can fail when upstream advisories affect currently resolved dependencies.

## Security design commitments

- Keep provider credentials server-side and out of logs.
- Treat repository files and model responses as untrusted input.
- Apply bounded input sizes, timeouts, and retries.
- Never execute AI-generated fixes automatically.
- Request only the GitHub permissions needed for the enabled feature.
- Clearly disclose when code is sent to a hosted model provider.
