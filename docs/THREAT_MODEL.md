# CodeGuard AI Threat Model

## Goal and scope
CodeGuard AI accepts source code and pull-request diffs that may be attacker-controlled. The goal is to produce bounded, advisory findings without executing repository content, disclosing secrets, or letting model output control application behavior.

## Trust boundaries

| Boundary | Trust | Required handling |
| --- | --- | --- |
| Submitted source, filenames, comments, strings and diffs | Untrusted | Bound size and paths; treat as data, never instructions; never execute |
| LLM/provider responses | Untrusted | Strict schema, path/line/evidence validation before persistence |
| Provider error text and bodies | Untrusted | Stable public errors; do not log exception text or provider response bodies |
| API keys, webhook secrets and database URLs | Secret | Keep server-side, do not add to prompts, redact from logs/errors |
| Suggested fixes | Untrusted proposals | Render as text for a human; never eval, execute or automatically apply |
| API, worker and logging infrastructure | Trusted computing base | Enforce size/time/retry limits and redact sensitive values |

## Threats and mitigations

- **Prompt injection in source/diffs:** system instructions explicitly mark repository-provided content as untrusted. Source is JSON-serialized and supplied as user content. Prompt wording is not a security sandbox, so model output must still be validated.
- **Hidden prompt or credential extraction:** credentials are configured server-side and not included in review input. Provider adapters map failures to safe exception types and avoid logging exception content.
- **Malformed or malicious model output:** strict response schemas reject extra fields and invalid values. The pipeline checks file scope, line bounds and cited evidence within supplied source lines. Invalid output is rejected rather than repaired or retried.
- **Resource exhaustion:** request body size, AI input bytes, file path length, provider timeouts and retry counts are bounded; exponential backoff is capped. Review-create rate limiting limits frequency. Worker/process concurrency must also be configured appropriately at deployment.
- **Secret leakage:** logs redact common bearer and key/value token forms. Evidence is redacted in the local review workflow. Regex masking is best-effort and cannot identify every credential format, so source must not be logged.
- **Unsafe fixes:** suggested fixes remain finding text. Application code never evaluates or applies them.

## Regression suite

Run `pytest backend/tests/test_adversarial_security.py` from the repository root or `pytest tests/test_adversarial_security.py` from `backend/`. Tests use fake clients only and do not call live providers.

## Residual risks

Prompt injection cannot be solved by prompt text alone. Secret-pattern matching can miss unknown formats. There is no dedicated global AI-review semaphore; configure API/worker concurrency according to resource budgets. Human review is required before suggested code changes are applied.
