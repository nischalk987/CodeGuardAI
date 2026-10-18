# Security Policy

## Scope

CodeGuard AI is an early-stage project. Its security controls and integrations are under active development; do not assume that planned mitigations already exist.

Areas of particular interest include secret handling, prompt injection through repository content, GitHub token permissions, unsafe processing of untrusted diffs, dependency vulnerabilities, and sensitive data in logs.

## Reporting a vulnerability

Please do **not** publish exploitable details, API keys, access tokens, private source code, or sensitive personal data in a public issue.

Use GitHub's private vulnerability reporting feature for this repository when available. If private reporting is not enabled, contact the repository owner through a private channel before disclosing details publicly. Include impact, reproduction steps, affected commit/version, and any safe proof of concept.

## Security design commitments

- Keep provider credentials server-side and out of logs.
- Treat repository files and model responses as untrusted input.
- Apply bounded input sizes, timeouts, and retries.
- Never execute AI-generated fixes automatically.
- Request only the GitHub permissions needed for the enabled feature.
- Clearly disclose when code is sent to a hosted model provider.

## Status

This policy describes intended engineering practice, not a claim that every control is already implemented.
