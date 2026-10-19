import asyncio
import json
import logging
from types import SimpleNamespace

import httpx
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
from app.core.config import Settings
from app.domain.enums import EvidenceCertainty, FindingSource
from app.infrastructure.ai.factory import configured_provider, create_ai_reviewer
from app.infrastructure.ai.huggingface_reviewer import (
    INFERENCE_URL,
    HuggingFaceAIReviewer,
)

SOURCE = 'password = "demo-value"\nprint(password)\n'
EVIDENCE = 'password = "demo-value"'
TEST_TOKEN = "hf_test_only_do_not_use"


def model_response() -> dict[str, object]:
    return {
        "choices": [{"message": {"content": json.dumps({
            "findings": [{
                "rule_id": "SEC-001",
                "severity": "high",
                "category": "Security",
                "message": "A hard-coded password is present.",
                "file_path": "src/app.py",
                "start_line": 1,
                "end_line": 1,
                "confidence": 70,
                "evidence": EVIDENCE,
                "suggested_fix": "Load the value from a secret manager.",
            }]
        })}}]
    }


class FakeResponse:
    def __init__(self, payload: object = None, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", INFERENCE_URL)
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("provider error", request=request, response=response)

    def json(self) -> object:
        return self.payload


class InvalidJsonResponse(FakeResponse):
    def json(self) -> object:
        raise json.JSONDecodeError("bad response", "not-json", 0)


class FakeClient:
    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def post(self, url: str, *, json: dict[str, object]) -> FakeResponse:
        self.calls.append((url, json))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome if isinstance(outcome, FakeResponse) else FakeResponse(outcome)


def make_reviewer(*outcomes: object, retries: int = 0, sleeper=None):
    settings = Settings(
        _env_file=None,
        ai_provider="huggingface",
        hf_token=TEST_TOKEN,
        hf_model="openai/gpt-oss-20b",
        hf_max_retries=retries,
    )
    client = FakeClient(*outcomes)
    delays: list[float] = []

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    reviewer = HuggingFaceAIReviewer(settings, client=client, sleeper=sleeper or record_sleep)
    return reviewer, client, delays


def test_huggingface_adapter_returns_validated_advisory_findings() -> None:
    reviewer, client, _ = make_reviewer(model_response())

    findings = asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.source is FindingSource.AI
    assert finding.certainty is EvidenceCertainty.HYPOTHESIS
    assert finding.severity.value == "high"
    assert finding.evidence == EVIDENCE
    assert client.calls[0][0] == INFERENCE_URL
    body = client.calls[0][1]
    assert body["model"] == "openai/gpt-oss-20b"
    assert body["response_format"]["type"] == "json_schema"
    assert PROMPT_VERSION in body["messages"][1]["content"]
    assert "untrusted repository data" in body["messages"][1]["content"]


def test_huggingface_rejects_invalid_provider_response() -> None:
    reviewer, client, _ = make_reviewer({"choices": []})
    with pytest.raises(AIReviewerInvalidResponse):
        asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))
    assert len(client.calls) == 1

    reviewer, _, _ = make_reviewer(InvalidJsonResponse())
    with pytest.raises(AIReviewerInvalidResponse):
        asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))


def test_huggingface_rejects_oversized_input_before_provider_call() -> None:
    settings = Settings(
        _env_file=None,
        ai_provider="huggingface",
        hf_token=TEST_TOKEN,
        ai_review_max_input_bytes=3,
    )
    client = FakeClient(model_response())
    reviewer = HuggingFaceAIReviewer(settings, client=client)
    with pytest.raises(AIReviewerInputError):
        asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))
    assert client.calls == []


def test_huggingface_timeout_retries_are_bounded_and_safe() -> None:
    reviewer, client, delays = make_reviewer(
        httpx.TimeoutException(TEST_TOKEN), FakeResponse(model_response()), retries=1
    )

    findings = asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))

    assert len(findings) == 1
    assert len(client.calls) == 2
    assert delays == [0.25]


def test_huggingface_final_timeout_and_rate_limit_are_safe() -> None:
    reviewer, client, _ = make_reviewer(httpx.TimeoutException(TEST_TOKEN))
    with pytest.raises(AIReviewerTimeout) as raised:
        asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))
    assert len(client.calls) == 1
    assert TEST_TOKEN not in str(raised.value)

    reviewer, _, _ = make_reviewer(FakeResponse(status_code=429), retries=3)
    with pytest.raises(AIReviewerRateLimited) as raised:
        asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))
    assert TEST_TOKEN not in str(raised.value)


def test_huggingface_provider_error_does_not_log_response_or_token(caplog) -> None:
    reviewer, client, _ = make_reviewer(FakeResponse(status_code=401), retries=2)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(AIReviewerProviderError) as raised:
            asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))
    assert len(client.calls) == 1
    assert TEST_TOKEN not in caplog.text
    assert TEST_TOKEN not in str(raised.value)


def test_transient_server_error_retries_and_returns_valid_result() -> None:
    reviewer, client, delays = make_reviewer(
        FakeResponse(status_code=503), FakeResponse(model_response()), retries=1
    )
    findings = asyncio.run(reviewer.review(file_path="src/app.py", source_code=SOURCE))
    assert len(findings) == 1
    assert len(client.calls) == 2
    assert delays == [0.25]


def test_provider_factory_uses_groq_by_default_and_huggingface_when_configured(monkeypatch) -> None:
    import app.infrastructure.ai.factory as provider_factory

    groq = object()
    huggingface = object()
    monkeypatch.setattr(provider_factory, "GroqAIReviewer", lambda _settings: groq)
    monkeypatch.setattr(provider_factory, "HuggingFaceAIReviewer", lambda _settings: huggingface)
    groq_settings = Settings(_env_file=None, groq_api_key="test-groq-key")
    assert create_ai_reviewer(groq_settings) is groq
    assert configured_provider(groq_settings) == ("Groq", "openai/gpt-oss-20b")

    hf_settings = Settings(_env_file=None, ai_provider="huggingface", hf_token=TEST_TOKEN)
    assert create_ai_reviewer(hf_settings) is huggingface
    assert configured_provider(hf_settings) == ("Hugging Face", "openai/gpt-oss-20b")


def test_huggingface_missing_token_fails_closed() -> None:
    with pytest.raises(AIReviewerNotConfigured):
        HuggingFaceAIReviewer(Settings(_env_file=None, ai_provider="huggingface"))


def test_client_uses_configured_timeout_and_backend_token(monkeypatch) -> None:
    initialized: dict[str, object] = {}

    def fake_client(**kwargs: object) -> object:
        initialized.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("app.infrastructure.ai.huggingface_reviewer.httpx.AsyncClient", fake_client)
    settings = Settings(
        _env_file=None, ai_provider="huggingface", hf_token=TEST_TOKEN, hf_timeout_seconds=9.5
    )
    reviewer = HuggingFaceAIReviewer(settings)

    assert reviewer._client is not None
    assert initialized == {
        "timeout": 9.5,
        "headers": {"Authorization": f"Bearer {TEST_TOKEN}"},
    }
