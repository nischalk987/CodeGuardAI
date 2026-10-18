# Contributing to CodeGuard AI

Thanks for contributing. CodeGuard AI is being built to demonstrate product thinking and sound engineering: evidence-based findings, reliable APIs, secure handling of untrusted code, and a polished developer experience.

## Before you start

1. Check the [open issues](https://github.com/nischalk987/CodeGuardAI/issues) and choose a clearly scoped task.
2. For a substantial change, open or comment on an issue first so the scope and acceptance criteria are agreed.
3. Avoid duplicating work already in progress.

## Development principles

- Keep HTTP routes thin; put business rules in application/domain modules.
- Keep provider SDKs behind interfaces so they can be mocked in tests.
- Treat repository content, model responses, and suggested fixes as untrusted input.
- Never execute generated fixes automatically.
- Keep API keys and private repository contents out of logs, screenshots, fixtures, and frontend bundles.
- Label seeded examples as demo data; do not describe planned features as implemented.
- Prefer focused pull requests that solve one issue.

## Pull request checklist

- [ ] The change addresses a linked issue or explains why it is needed.
- [ ] Tests cover new behavior and important error cases.
- [ ] Lint, type checks, and relevant tests pass.
- [ ] API or configuration changes are documented.
- [ ] No credentials, private code, or personal data are committed.
- [ ] Security and failure modes are considered.
- [ ] README and screenshots are updated only when they accurately reflect working functionality.

## Commit and review expectations

Use descriptive commit messages such as `feat: add review status model`, `fix: reject malformed finding ranges`, or `docs: explain local setup`. Keep the change reviewable and describe trade-offs in the PR description.

## Reporting security concerns

Do not publish exploitable vulnerabilities, credentials, or private source code in a public issue. See [SECURITY.md](SECURITY.md).
