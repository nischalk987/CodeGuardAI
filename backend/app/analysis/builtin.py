"""Small deterministic local rules that need no external analyzer binary."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator, Sequence

from app.analysis.base import AnalyzerError
from app.domain import Finding, FindingSource, Severity

SUPPORTED_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
MAX_FILE_BYTES = 1_000_000
MAX_FILES = 10_000
_RULES = (
    (
        "CG.SEC.HARDCODED_CREDENTIAL",
        Severity.HIGH,
        "Security",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|token)\s*[:=]\s*(['\"])([^'\"]{4,})\1"
        ),
        "A credential-like value is assigned directly in source code.",
        "Load credentials from a secret manager or environment variable.",
    ),
    (
        "CG.SEC.DYNAMIC_EXECUTION",
        Severity.HIGH,
        "Security",
        re.compile(r"\b(?:eval|exec)\s*\("),
        "Dynamic code execution can run input as code.",
        "Avoid evaluating untrusted input; use a constrained parser or explicit dispatch.",
    ),
    (
        "CG.SEC.SUBPROCESS_SHELL_TRUE",
        Severity.HIGH,
        "Security",
        re.compile(r"\bshell\s*=\s*True\b"),
        "A subprocess uses a shell, which can make argument injection possible.",
        "Pass an argument list and keep shell execution disabled.",
    ),
    (
        "CG.SEC.TLS_VERIFY_DISABLED",
        Severity.HIGH,
        "Security",
        re.compile(r"\bverify\s*=\s*False\b"),
        "TLS certificate verification is disabled for this request.",
        "Enable certificate verification and configure a trusted CA if needed.",
    ),
)
_PLACEHOLDERS = {"example", "changeme", "change-me", "dummy", "placeholder", "test", "xxx"}
_DEFAULT_IGNORES = {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}


class BuiltinAnalyzer:
    """Deterministic, bounded rules over source text; no code is executed or uploaded."""

    name = "codeguard-builtin"
    version = "1.0"

    def analyze(self, target: Path, *, ignored_paths: Sequence[str] = ()) -> list[Finding]:
        target = target.resolve()
        if not target.exists():
            raise AnalyzerError(f"Scan target does not exist: {target}")
        if not (target.is_file() or target.is_dir()):
            raise AnalyzerError(f"Scan target is not a regular file or directory: {target}")

        ignored = tuple(_DEFAULT_IGNORES | {_normalize_ignore(value) for value in ignored_paths})
        findings: list[Finding] = []
        supported_count = 0
        if target.is_file():
            candidates = iter((target,))
        else:
            candidates = _walk_files(target, ignored)
        for index, path in enumerate(candidates, start=1):
            if index > MAX_FILES:
                raise AnalyzerError(f"Scan exceeds the {MAX_FILES} file limit")
            relative = path.name if target.is_file() else path.relative_to(target).as_posix()
            if target.is_file() and _is_ignored(relative, ignored):
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            supported_count += 1
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                raise AnalyzerError(f"Unable to read source file {relative}: {exc.strerror or 'I/O error'}") from None
            findings.extend(self._analyze_source(source, relative))

        if target.is_file() and supported_count == 0:
            suffix = target.suffix or "(no extension)"
            raise AnalyzerError(f"Unsupported file type {suffix}; supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}")
        return findings

    def analyze_source(self, source: str, file_path: str) -> list[Finding]:
        """Analyze bounded source text without writing it to disk or executing it."""
        path = Path(file_path)
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise AnalyzerError(
                f"Unsupported file type {path.suffix or '(no extension)'}; "
                f"supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
            )
        if len(source.encode("utf-8")) > MAX_FILE_BYTES:
            raise AnalyzerError(f"Source exceeds the {MAX_FILE_BYTES} byte file limit")
        return self._analyze_source(source, path.as_posix())

    def _analyze_source(self, source: str, relative: str) -> list[Finding]:
        findings: list[Finding] = []
        for line_number, line in enumerate(source.splitlines(), start=1):
            for rule_id, severity, category, pattern, message, fix in _RULES:
                match = pattern.search(line)
                if not match:
                    continue
                if rule_id == "CG.SEC.HARDCODED_CREDENTIAL":
                    value = match.group(2).strip().lower()
                    if value in _PLACEHOLDERS or value.startswith(("your_", "your-")):
                        continue
                findings.append(
                    Finding(
                        rule_id=rule_id,
                        source=FindingSource.STATIC,
                        severity=severity,
                        category=category,
                        message=message,
                        file_path=relative,
                        start_line=line_number,
                        end_line=line_number,
                        confidence=85,
                        evidence=line.strip()[:500],
                        analyzer_name=self.name,
                        analyzer_version=self.version,
                        suggested_fix=fix,
                    )
                )
        return findings


def _normalize_ignore(value: str) -> str:
    return value.replace("\\", "/").strip("/")


def _is_ignored(relative_path: str, ignored_paths: Sequence[str]) -> bool:
    normalized = relative_path.replace("\\", "/")
    return any(
        normalized == ignored or normalized.startswith(f"{ignored}/")
        for ignored in ignored_paths
        if ignored
    )


def _walk_files(target: Path, ignored_paths: Sequence[str]) -> Iterator[Path]:
    """Yield files in stable order while pruning default/user ignored directories."""
    count = 0
    for root, directories, filenames in os.walk(target, followlinks=False):
        root_path = Path(root)
        directories[:] = sorted(
            directory
            for directory in directories
            if not (root_path / directory).is_symlink()
            and not _is_ignored((root_path / directory).relative_to(target).as_posix(), ignored_paths)
        )
        for filename in sorted(filenames):
            path = root_path / filename
            if path.is_symlink() or not path.is_file():
                continue
            count += 1
            if count > MAX_FILES:
                raise AnalyzerError(f"Scan exceeds the {MAX_FILES} file limit")
            yield path
