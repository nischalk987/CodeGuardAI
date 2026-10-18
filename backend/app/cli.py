"""CodeGuard's local, CI-friendly command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from app.analysis import AnalyzerError, BuiltinAnalyzer, CodeAnalyzer, SemgrepAnalyzer
from app.ai.exceptions import AIReviewerError
from app.core.config import get_settings
from app.domain import Finding, Severity

_SEVERITY_ORDER = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
}
_EXIT_FINDINGS = 1
_EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codeguard", description="Analyze source files locally.")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="scan a local file or directory")
    scan.add_argument("target", type=Path, help="local source file or directory")
    scan.add_argument("--analyzer", choices=("builtin", "semgrep", "all"), default="builtin")
    scan.add_argument("--semgrep-config", default="auto", help="Semgrep ruleset or local config file")
    scan.add_argument("--format", choices=("text", "json"), default="text")
    scan.add_argument(
        "--fail-on",
        choices=("none", "critical", "high", "medium", "low"),
        default="none",
        help="exit 1 when a finding at or above this severity is present",
    )
    scan.add_argument("--timeout", type=_parse_timeout, default=120.0, help="Semgrep timeout (1 to 600 seconds)")
    scan.add_argument("--ignore", action="append", default=[], metavar="PATH", help="ignore a path, repeatable")
    scan.add_argument(
        "--ai-review",
        action="store_true",
        help="explicitly send one source file to Groq for advisory AI review",
    )
    return parser


def _parse_timeout(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a number") from None
    if not math.isfinite(seconds) or not 0 < seconds <= 600:
        raise argparse.ArgumentTypeError("timeout must be greater than zero and at most 600 seconds")
    return seconds


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "scan":
        parser.error("a command is required")
    try:
        target = args.target.expanduser().resolve(strict=True)
        if not (target.is_file() or target.is_dir()):
            raise AnalyzerError("Scan target must be a local file or directory")
        if args.ai_review and target.is_dir():
            raise AnalyzerError("AI review accepts one source file only; directory contents are never sent")
        analyzers: list[CodeAnalyzer]
        if args.analyzer == "builtin":
            analyzers = [BuiltinAnalyzer()]
        elif args.analyzer == "semgrep":
            analyzers = [SemgrepAnalyzer(config=args.semgrep_config, timeout_seconds=args.timeout)]
        else:
            analyzers = [
                BuiltinAnalyzer(),
                SemgrepAnalyzer(config=args.semgrep_config, timeout_seconds=args.timeout),
            ]
        findings = [
            finding
            for analyzer in analyzers
            for finding in analyzer.analyze(target, ignored_paths=args.ignore)
        ]
        if args.ai_review:
            ai_findings = _run_ai_review(target)
            findings.extend(ai_findings)
    except (AnalyzerError, OSError) as exc:
        print(f"codeguard: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    except AIReviewerError as exc:
        print(f"codeguard: {exc.safe_message}", file=sys.stderr)
        return _EXIT_ERROR

    groups = _group_findings(findings)
    if args.format == "json":
        print(json.dumps(_report(target, analyzers, groups, ai_review_requested=args.ai_review), indent=2, sort_keys=True))
    else:
        _print_text(target, analyzers, groups, ai_review_requested=args.ai_review)
    threshold = None if args.fail_on == "none" else Severity(args.fail_on)
    if threshold and any(
        _SEVERITY_ORDER[finding.severity] >= _SEVERITY_ORDER[threshold]
        for finding in findings
    ):
        return _EXIT_FINDINGS
    return 0


def _run_ai_review(target: Path) -> list[Finding]:
    from app.analysis.builtin import MAX_FILE_BYTES, SUPPORTED_SUFFIXES
    from app.infrastructure.ai.groq_reviewer import GroqAIReviewer
    from pydantic import ValidationError

    if target.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise AnalyzerError(
            f"AI review supports these source file types: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    try:
        settings = get_settings()
    except ValidationError:
        raise AnalyzerError("AI review environment settings are invalid; check backend configuration") from None
    if settings.groq_api_key is None:
        raise AnalyzerError("AI review is opt-in and requires GROQ_API_KEY in the backend environment")
    if target.stat().st_size > min(MAX_FILE_BYTES, settings.ai_review_max_input_bytes):
        raise AnalyzerError("AI review input exceeds the configured per-file size limit")
    try:
        source_code = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise AnalyzerError("AI review could not read the source file as UTF-8") from None
    working_directory = Path.cwd().resolve()
    try:
        file_path = target.relative_to(working_directory).as_posix()
    except ValueError:
        file_path = target.name
    reviewer = GroqAIReviewer(settings)
    print(
        "AI review opted in: this source file will be sent to Groq for advisory analysis. "
        "No other file will be sent.",
        file=sys.stderr,
    )
    findings = asyncio.run(reviewer.review(file_path=file_path, source_code=source_code))
    return [
        replace(
            finding,
            analyzer_name="groq-ai-reviewer",
            analyzer_version=f"{settings.groq_model}/v1",
        )
        for finding in findings
    ]


def _group_findings(findings: Sequence[Finding]) -> list[list[Finding]]:
    groups: dict[tuple[str, int, int, str], list[Finding]] = defaultdict(list)
    for finding in findings:
        key = (
            finding.file_path,
            finding.start_line,
            finding.end_line,
            finding.evidence.strip(),
        )
        groups[key].append(finding)
    return [groups[key] for key in sorted(groups)]


def _finding_data(finding: Finding) -> dict[str, object]:
    return {
        "id": finding.id,
        "rule_id": finding.rule_id,
        "source": finding.source.value,
        "analyzer_name": finding.analyzer_name,
        "analyzer_version": finding.analyzer_version,
        "severity": finding.severity.value,
        "category": finding.category,
        "message": finding.message,
        "file_path": finding.file_path,
        "start_line": finding.start_line,
        "end_line": finding.end_line,
        "confidence": finding.confidence,
        "certainty": finding.certainty.value,
        "evidence": finding.evidence,
        "suggested_fix": finding.suggested_fix,
    }


def _report(
    target: Path,
    analyzers: Sequence[CodeAnalyzer],
    groups: list[list[Finding]],
    *,
    ai_review_requested: bool,
) -> dict[str, object]:
    totals = Counter(finding.severity.value for group in groups for finding in group)
    return {
        "schema_version": "1.0",
        "scan": {
            "target": str(target),
            "analyzers": [
                {"name": analyzer.name, "version": getattr(analyzer, "version", "unknown")}
                for analyzer in analyzers
            ],
            "source_uploaded": ai_review_requested,
            "ai_review": {
                "requested": ai_review_requested,
                "provider": "Groq" if ai_review_requested else None,
                "disclosure": (
                    "One source file was sent to Groq after explicit --ai-review opt-in"
                    if ai_review_requested
                    else "not requested; no source file was sent"
                ),
            },
        },
        "summary": {
            "finding_count": sum(len(group) for group in groups),
            "group_count": len(groups),
            "critical": totals["critical"],
            "high": totals["high"],
            "medium": totals["medium"],
            "low": totals["low"],
        },
        "finding_groups": [
            {
                "duplicate_count": len(group) - 1,
                "findings": [_finding_data(finding) for finding in group],
            }
            for group in groups
        ],
    }


def _print_text(
    target: Path,
    analyzers: Sequence[CodeAnalyzer],
    groups: list[list[Finding]],
    *,
    ai_review_requested: bool,
) -> None:
    names = ", ".join(analyzer.name for analyzer in analyzers)
    upload_note = "yes (one file to Groq, explicit opt-in)" if ai_review_requested else "no"
    print(f"CodeGuard local scan: {target}\nAnalyzers: {names} | Source uploaded: {upload_note}")
    if not groups:
        print("No findings.")
        return
    for group in groups:
        finding = group[0]
        line_range = (
            str(finding.start_line)
            if finding.start_line == finding.end_line
            else f"{finding.start_line}-{finding.end_line}"
        )
        provenance = ", ".join(
            f"{item.analyzer_name or item.source.value}@{item.analyzer_version or 'unknown'}"
            for item in group
        )
        print(
            f"{finding.severity.value.upper():8} {finding.file_path}:{line_range}"
            f" [{finding.rule_id}] {finding.message} (via {provenance})"
        )
        if len(group) > 1:
            print(f"         Also reported by: {provenance}")
    print(f"\n{sum(len(group) for group in groups)} finding(s) in {len(groups)} group(s).")


if __name__ == "__main__":
    raise SystemExit(main())
