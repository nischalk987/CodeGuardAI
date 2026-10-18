"""Optional local Semgrep CLI adapter using its JSON output."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from app.analysis.base import AnalyzerError, AnalyzerOutputError, AnalyzerTimeoutError
from app.domain import Finding, FindingSource, Severity

Runner = Callable[..., subprocess.CompletedProcess[str]]
_SEVERITIES = {
    "ERROR": Severity.HIGH,
    "WARNING": Severity.MEDIUM,
    "INFO": Severity.LOW,
    "INVENTORY": Severity.LOW,
}
_CONFIDENCE = {"HIGH": 90, "MEDIUM": 70, "LOW": 50}


class SemgrepAnalyzer:
    """Run Semgrep locally with telemetry disabled and bounded subprocess resources."""

    name = "semgrep"

    def __init__(
        self,
        *,
        config: str = "auto",
        timeout_seconds: float = 120,
        max_target_bytes: int = 1_000_000,
        executable: str = "semgrep",
        runner: Runner = subprocess.run,
    ) -> None:
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 600:
            raise ValueError("timeout_seconds must be greater than zero and no more than 600")
        if max_target_bytes <= 0:
            raise ValueError("max_target_bytes must be greater than zero")
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.max_target_bytes = max_target_bytes
        self.executable = executable
        self.runner = runner

    def analyze(self, target: Path, *, ignored_paths: Sequence[str] = ()) -> list[Finding]:
        target = target.resolve()
        if not target.exists():
            raise AnalyzerError(f"Scan target does not exist: {target}")
        if not (target.is_file() or target.is_dir()):
            raise AnalyzerError(f"Scan target is not a regular file or directory: {target}")
        executable_path = shutil.which(self.executable)
        if not executable_path and self.runner is subprocess.run:
            raise AnalyzerError("Semgrep is not installed or not on PATH. Install it with: python -m pip install semgrep")
        command = [
            executable_path or self.executable,
            "scan",
            "--json",
            "--config",
            self.config,
            "--metrics=off",
            "--jobs",
            "1",
            "--timeout",
            str(max(1, int(self.timeout_seconds))),
            "--max-target-bytes",
            str(self.max_target_bytes),
        ]
        for ignored_path in ignored_paths:
            command.extend(("--exclude", ignored_path))
        command.append(str(target))
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AnalyzerTimeoutError(
                f"Semgrep exceeded the {self.timeout_seconds:g} second timeout"
            ) from exc
        except OSError as exc:
            raise AnalyzerError(f"Could not start Semgrep: {exc.strerror or 'process error'}") from None
        if completed.returncode != 0:
            details = (completed.stderr or "").strip().splitlines()
            reason = details[-1][:300] if details else f"exit code {completed.returncode}"
            raise AnalyzerError(f"Semgrep failed: {reason}")
        try:
            payload = json.loads(completed.stdout)
        except (TypeError, json.JSONDecodeError):
            raise AnalyzerOutputError("Semgrep returned malformed JSON output") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise AnalyzerOutputError("Semgrep JSON output is missing a results list")
        version = payload.get("version")
        if not isinstance(version, str) or not version.strip():
            version = "unknown"
        findings: list[Finding] = []
        for index, result in enumerate(payload["results"]):
            findings.append(_normalize_result(result, target, version, index))
        return findings


def _normalize_result(result: object, target: Path, version: str, index: int) -> Finding:
    if not isinstance(result, dict):
        raise AnalyzerOutputError(f"Semgrep result {index} is not an object")
    try:
        rule_id = _required_string(result, "check_id")
        message = _required_string(result, "extra.message")
        raw_path = _required_string(result, "path")
        extra = result.get("extra")
        start = result.get("start")
        end = result.get("end")
        if not isinstance(extra, dict) or not isinstance(start, dict) or not isinstance(end, dict):
            raise ValueError("missing location or extra fields")
        severity_label = str(extra.get("severity", "WARNING")).upper()
        severity = _SEVERITIES.get(severity_label, Severity.MEDIUM)
        metadata = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
        category_value = metadata.get("category", "Security")
        category = category_value if isinstance(category_value, str) else str(category_value)
        confidence_value = str(metadata.get("confidence", "MEDIUM")).upper()
        confidence = _CONFIDENCE.get(confidence_value, 70)
        evidence = extra.get("lines")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("missing original source evidence")
        suggestion = extra.get("fix")
        file_path = _relative_path(raw_path, target)
        start_line = start.get("line")
        end_line = end.get("line")
        return Finding(
            rule_id=rule_id,
            source=FindingSource.STATIC,
            severity=severity,
            category=category,
            message=message,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            confidence=confidence,
            evidence=evidence,
            analyzer_name="semgrep",
            analyzer_version=version,
            suggested_fix=suggestion if isinstance(suggestion, str) and suggestion.strip() else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        message = str(exc) or "invalid finding fields"
        raise AnalyzerOutputError(f"Semgrep result {index} is invalid: {message}") from None


def _required_string(value: dict[str, object], key: str) -> str:
    if key == "extra.message":
        extra = value.get("extra")
        result = extra.get("message") if isinstance(extra, dict) else None
    else:
        result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"missing {key}")
    return result.strip()


def _relative_path(raw_path: str, target: Path) -> str:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        scan_root = target if target.is_dir() else target.parent
        alternatives = ((scan_root / candidate).resolve(), (Path.cwd() / candidate).resolve())
        existing = [path for path in alternatives if path.exists()]
        candidate = existing[0] if existing else alternatives[0]
    else:
        candidate = candidate.resolve()
    try:
        return candidate.relative_to(target if target.is_dir() else target.parent).as_posix()
    except ValueError:
        raise ValueError("finding path is outside the scan target") from None
