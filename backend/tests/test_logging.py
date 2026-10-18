import json
import logging

from app.core.logging import JsonFormatter


def test_json_logging_redacts_sensitive_fields_and_message_values() -> None:
    record = logging.LogRecord(
        name="codeguard.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="review started token=inline-token client_secret=private-value Authorization: Bearer bearer-token",
        args=(),
        exc_info=None,
    )
    record.api_key = "field-api-key"
    record.review_id = "review-123"

    payload = json.loads(JsonFormatter().format(record))

    rendered = json.dumps(payload)
    assert payload["review_id"] == "review-123"
    assert payload["api_key"] == "[REDACTED]"
    assert "inline-token" not in rendered
    assert "private-value" not in rendered
    assert "bearer-token" not in rendered
    assert "field-api-key" not in rendered
    assert payload["level"] == "INFO"
