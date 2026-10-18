import json
import subprocess
from pathlib import Path

import pytest

from app.analysis import (
    AnalyzerError,
    AnalyzerOutputError,
    AnalyzerTimeoutError,
    BuiltinAnalyzer,
    SemgrepAnalyzer,
)
from app.domain import FindingSource, Severity

FIXTURES = Path(__file__).parent / "fixtures"


def test_builtin_fixture_findings_are_deterministic_and_normalized() -> None:
    first = BuiltinAnalyzer().analyze(FIXTURES / "static_sample.py")
    second = BuiltinAnalyzer().analyze(FIXTURES / "static_sample.py")

    assert [finding.id for finding in first] == [finding.id for finding in second]
    assert [finding.rule_id for finding in first] == [
        "CG.SEC.HARDCODED_CREDENTIAL",
        "CG.SEC.DYNAMIC_EXECUTION",
        "CG.SEC.SUBPROCESS_SHELL_TRUE",
        "CG.SEC.TLS_VERIFY_DISABLED",
    ]
    assert all(finding.source is FindingSource.STATIC for finding in first)
    assert all(finding.analyzer_name == "codeguard-builtin" for finding in first)
    assert [(finding.start_line, finding.end_line) for finding in first] == [
        (1, 1), (2, 2), (3, 3), (4, 4)
    ]


def test_builtin_analyzes_source_in_memory_with_repository_relative_path() -> None:
    source = 'password = "private-value"\nresult = eval(user_input)\n'

    findings = BuiltinAnalyzer().analyze_source(source, "src/auth.py")

    assert [finding.file_path for finding in findings] == ["src/auth.py", "src/auth.py"]
    assert [finding.start_line for finding in findings] == [1, 2]
    assert [finding.rule_id for finding in findings] == [
        "CG.SEC.HARDCODED_CREDENTIAL",
        "CG.SEC.DYNAMIC_EXECUTION",
    ]


def test_builtin_ignores_requested_directory_and_safe_fixture_is_clean(tmp_path: Path) -> None:
    ignored = tmp_path / "ignored"
    ignored.mkdir()
    (ignored / "bad.py").write_text("result = eval(user_input)\n", encoding="utf-8")
    (tmp_path / "safe.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    findings = BuiltinAnalyzer().analyze(tmp_path, ignored_paths=["ignored"])
    assert findings == []
    assert BuiltinAnalyzer().analyze(FIXTURES / "safe_sample.py") == []


def test_builtin_rejects_unsupported_direct_file_and_missing_target() -> None:
    with pytest.raises(AnalyzerError, match="Unsupported file type"):
        BuiltinAnalyzer().analyze(FIXTURES / "semgrep-results.json")
    with pytest.raises(AnalyzerError, match="does not exist"):
        BuiltinAnalyzer().analyze(FIXTURES / "missing.py")


def test_semgrep_normalizes_fixture_and_preserves_provenance(tmp_path: Path) -> None:
    target = tmp_path / "project"
    (target / "src").mkdir(parents=True)
    (target / "src" / "example.py").write_text("result = eval(user_input)\n", encoding="utf-8")
    fixture = json.loads((FIXTURES / "semgrep-results.json").read_text(encoding="utf-8"))
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, json.dumps(fixture), "")

    findings = SemgrepAnalyzer(runner=runner).analyze(target, ignored_paths=["vendor"])
    finding = findings[0]

    assert finding.rule_id == "python.lang.security.audit.dynamic-eval"
    assert finding.source is FindingSource.STATIC
    assert finding.severity is Severity.HIGH
    assert finding.file_path == "src/example.py"
    assert finding.start_line == 7 and finding.end_line == 7
    assert finding.evidence == "result = eval(user_input)"
    assert finding.analyzer_name == "semgrep" and finding.analyzer_version == "1.129.0"
    command, kwargs = calls[0]
    assert "--metrics=off" in command
    assert command[command.index("--exclude") + 1] == "vendor"
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 120


def test_semgrep_reports_malformed_output_and_timeout_clearly(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('safe')", encoding="utf-8")

    def malformed(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "not-json", "")

    with pytest.raises(AnalyzerOutputError, match="malformed JSON"):
        SemgrepAnalyzer(runner=malformed).analyze(target)

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    with pytest.raises(AnalyzerTimeoutError, match="timeout"):
        SemgrepAnalyzer(runner=timeout).analyze(target)

    def missing_results(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, '{"version":"1.0"}', "")

    with pytest.raises(AnalyzerOutputError, match="missing a results list"):
        SemgrepAnalyzer(runner=missing_results).analyze(target)


def test_semgrep_missing_binary_is_actionable(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('safe')", encoding="utf-8")
    monkeypatch.setattr("app.analysis.semgrep.shutil.which", lambda _name: None)

    with pytest.raises(AnalyzerError, match="Semgrep is not installed"):
        SemgrepAnalyzer(executable="missing-semgrep-binary").analyze(target)


def test_semgrep_nonzero_exit_does_not_echo_unbounded_output(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('safe')", encoding="utf-8")

    def failed(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, "", "configuration failed\n" + "x" * 500)

    with pytest.raises(AnalyzerError, match="Semgrep failed") as error:
        SemgrepAnalyzer(runner=failed).analyze(target)
    assert len(str(error.value)) < 400
