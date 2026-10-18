import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(authorization|api[_-]?key|private[_-]?key|credential|token|password|secret)", re.I
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_ASSIGNMENT = re.compile(
    r"(?i)(\b[\w-]*(?:authorization|api[_-]?key|private[_-]?key|credential|token|password|secret)\b\s*[:=]\s*)([^\s,;]+)"
)


def _redact_text(value: str) -> str:
    value = _BEARER.sub("Bearer [REDACTED]", value)
    return _ASSIGNMENT.sub(r"\1[REDACTED]", value)


def _safe_value(value: Any, key: str = "") -> Any:
    if key and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {str(item_key): _safe_value(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value))


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per record and redact common credential shapes."""

    _standard_fields = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in self._standard_fields and not key.startswith("_"):
                payload[key] = _safe_value(value, key)
        if record.exc_info:
            payload["exception"] = _redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def configure_logging(level: str) -> None:
    """Configure consistent JSON logs for the API process."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
