import asyncio
import json
import logging
from types import SimpleNamespace

import pytest

from app.ai.exceptions import (
    AIReviewerInputError,
    AIReviewerInvalidResponse,
    AIReviewerNotConfigured,
    AIReviewerProviderError,
    AIReviewerRateLimited,
    AIReviewerTimeout,
)
from app.ai.prompts import PROMPT_VERSION
from app.ai.reviewer import AIReviewer
from app.core.config import Settings
from app.domain.enums import EvidenceCertainty, FindingSource
from app.infrastructure.ai.groq_reviewer import GroqAIReviewer
from app.infrastructure.ai import groq_reviewer as groq_module

SOURCE = 'password = "demo-value"\nprint(password)\n'
EVIDENCE = 'password = "demo-value"'
TEST_KEY = "gsk_test_only_do_not_use"


def model_response(*, file_path: str = "src/app.py", evidence: str = EVIDENCE) -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "rule_id": "SEC-001",
                    "severity": "high",
                    "category": "Security",
                    "message": "A hard-coded password is present.",
                    "file_path": file_path,
                    "start_line": 1,
                    "end_line": 1,
                    "confidence": 70,
                    "evidence": evidence,
                    "suggested_fix": "Load the value from a secret manager.",
                }
            ]
        }
    )


class MockCompletions:
    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))])


def make_reviewer(
    *outcomes: object,
    retries: int = 0,
    max_input_bytes: int = 40_000,
    sleeper=None,
) -> tuple[GroqAIReviewer, MockCompletions]:
    completions = MockCompletions(*outcomes)
    settings = Settings(
        _env_file=None,
        groq_api_key=TEST_KEY,
        groq_model="test/model",
        groq_max_retries=retries,
        ai_review_max_input_bytes=max_input_bytes,
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    reviewer = GroqAIReviewer(settings, client=client, sleeper=sleeper or _no_sleep)
    return reviewer, completions


async def _no_sleep(_seconds: float) -> None:
    return None


def test_groq_adapter_returns_validated_advisory_domain_findings() -> None:
    reviewer, client = make_reviewer(model_response())

    findings = asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.source is FindingSource.AI
    assert finding.certainty is EvidenceCertainty.HYPOTHESIS
    assert finding.severity.value == "high"
    assert finding.start_line == finding.end_line == 1
    assert finding.evidence == EVIDENCE
    assert client.calls[0]["model"] == "test/model"
    assert client.calls[0]["response_format"]["type"] == "json_schema"
    user_prompt = client.calls[0]["messages"][1]["content"]
    assert PROMPT_VERSION in user_prompt
    assert "untrusted repository data" in user_prompt


def test_empty_findings_response_is_valid() -> None:
    reviewer, _ = make_reviewer('{"findings": []}')
    assert asyncio.run(reviewer.review(file_path="main.py", source_code="pass\n")) == []


@pytest.mark.parametrize(
    ("source_code", "file_path"),
    [
        ("", "main.py"),
        ("01234567890", "main.py"),
        ("pass", "../outside.py"),
        ("pass", "src/../outside.py"),
        ("pass", "C:\\secrets.py"),
        ("pass", "/etc/passwd"),
    ],
)
def test_invalid_or_oversized_input_is_rejected_before_provider_call(
    source_code: str, file_path: str
) -> None:
    reviewer, client = make_reviewer("{\"findings\": []}", max_input_bytes=10)

    with pytest.raises(AIReviewerInputError):
        asyncio.run(reviewer.review(file_path=file_path, source_code=source_code))
    assert client.calls == []


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"findings": [{"severity": "urgent"}]}',
        model_response(file_path="another.py"),
        model_response(evidence="fake evidence"),
        model_response().replace('"start_line": 1', '"start_line": 0'),
        model_response().replace('"confidence": 70', '"confidence": 101'),
        model_response().replace('"confidence": 70', '"confidence": "70"'),
        model_response().replace('"findings": [', '"extra": "value", "findings": ['),
    ],
)
def test_malformed_or_out_of_scope_model_output_is_rejected(content: str) -> None:
    reviewer, client = make_reviewer(content, retries=2)

    with pytest.raises(AIReviewerInvalidResponse):
        asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))
    assert len(client.calls) == 1  # Invalid model output is rejected, not silently repaired.


def test_missing_api_key_fails_closed() -> None:
    with pytest.raises(AIReviewerNotConfigured):
        GroqAIReviewer(Settings(_env_file=None))


def test_groq_sdk_receives_backend_secret_and_configured_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialized: dict[str, object] = {}
    fake_client = object()

    def fake_groq(**kwargs: object) -> object:
        initialized.update(kwargs)
        return fake_client

    monkeypatch.setattr(groq_module, "AsyncGroq", fake_groq)
    settings = Settings(
        _env_file=None,
        groq_api_key=TEST_KEY,
        groq_timeout_seconds=7.5,
    )

    reviewer = GroqAIReviewer(settings)

    assert reviewer._client is fake_client
    assert initialized == {"api_key": TEST_KEY, "timeout": 7.5, "max_retries": 0}


def test_timeout_uses_bounded_retries_then_returns_safe_error() -> None:
    delays: list[float] = []

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    reviewer, client = make_reviewer(
        TimeoutError(TEST_KEY),
        TimeoutError(TEST_KEY),
        retries=1,
        sleeper=record_sleep,
    )

    with pytest.raises(AIReviewerTimeout) as raised:
        asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))
    assert len(client.calls) == 2
    assert delays == [0.25]
    assert TEST_KEY not in str(raised.value)


def test_rate_limit_is_handled_without_retry_or_provider_details() -> None:
    rate_limit = RuntimeError(TEST_KEY)
    rate_limit.status_code = 429  # type: ignore[attr-defined]
    reviewer, client = make_reviewer(rate_limit, retries=3)

    with pytest.raises(AIReviewerRateLimited) as raised:
        asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))
    assert len(client.calls) == 1
    assert TEST_KEY not in str(raised.value)


def test_transient_provider_failure_is_retried_and_succeeds() -> None:
    server_error = RuntimeError(TEST_KEY)
    server_error.status_code = 503  # type: ignore[attr-defined]
    reviewer, client = make_reviewer(server_error, model_response(), retries=1)

    findings = asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))

    assert len(findings) == 1
    assert len(client.calls) == 2


def test_provider_error_is_safe_and_does_not_log_secret(caplog: pytest.LogCaptureFixture) -> None:
    provider_error = RuntimeError(TEST_KEY)
    provider_error.status_code = 401  # type: ignore[attr-defined]
    reviewer, client = make_reviewer(provider_error, retries=2)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(AIReviewerProviderError) as raised:
            asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))

    assert len(client.calls) == 1
    assert TEST_KEY not in str(raised.value)
    assert TEST_KEY not in caplog.text


def test_fake_reviewer_implements_provider_independent_interface() -> None:
    class FakeReviewer:
        async def review(self, *, file_path: str, source_code: str):
            return []

    fake: AIReviewer = FakeReviewer()
    assert asyncio.run(fake.review(file_path="file.py", source_code="pass")) == []
