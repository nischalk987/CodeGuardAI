import json
from pathlib import Path

import pytest

import app.cli as cli
from app.analysis import AnalyzerError

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_default_text_reports_findings_and_threshold_exit(capsys) -> None:
    status = cli.main(["scan", str(FIXTURES / "static_sample.py"), "--fail-on", "high"])
    output = capsys.readouterr().out

    assert status == 1
    assert "Source uploaded: no" in output
    assert "static_sample.py:1 [CG.SEC.HARDCODED_CREDENTIAL]" in output


def test_cli_json_is_machine_readable_and_default_does_not_request_ai(capsys) -> None:
    status = cli.main(["scan", str(FIXTURES / "safe_sample.py"), "--format", "json"])
    output = capsys.readouterr().out
    report = json.loads(output)

    assert status == 0
    assert report["scan"]["source_uploaded"] is False
    assert report["scan"]["ai_review"]["requested"] is False
    assert report["scan"]["ai_review"]["provider"] is None
    assert report["summary"]["finding_count"] == 0
    assert report["finding_groups"] == []


def test_cli_can_fail_on_high_but_pass_at_medium(capsys) -> None:
    target = FIXTURES / "static_sample.py"
    assert cli.main(["scan", str(target), "--fail-on", "medium"]) == 1
    capsys.readouterr()
    assert cli.main(["scan", str(target), "--fail-on", "none"]) == 0


def test_cli_prints_clear_analyzer_error(monkeypatch, capsys, tmp_path: Path) -> None:
    class BrokenAnalyzer:
        name = "broken"
        version = "1"

        def analyze(self, target, *, ignored_paths=()):
            raise AnalyzerError("Semgrep is not installed")

    monkeypatch.setattr(cli, "BuiltinAnalyzer", BrokenAnalyzer)
    status = cli.main(["scan", str(tmp_path)])
    captured = capsys.readouterr()

    assert status == 2
    assert "Semgrep is not installed" in captured.err


def test_duplicate_group_retains_each_analyzer_provenance() -> None:
    from app.analysis import BuiltinAnalyzer

    finding = BuiltinAnalyzer().analyze(FIXTURES / "static_sample.py")[0]
    duplicate = type(finding)(
        rule_id="semgrep.duplicate-rule",
        source=finding.source,
        severity=finding.severity,
        category=finding.category,
        message=finding.message,
        file_path=finding.file_path,
        start_line=finding.start_line,
        end_line=finding.end_line,
        confidence=finding.confidence,
        evidence=finding.evidence,
        analyzer_name="semgrep",
        analyzer_version="1.2",
    )
    group = cli._group_findings([finding, duplicate])
    assert len(group) == 1
    assert {item.analyzer_name for item in group[0]} == {"codeguard-builtin", "semgrep"}
    assert {item.rule_id for item in group[0]} == {finding.rule_id, "semgrep.duplicate-rule"}


@pytest.mark.parametrize("args", [["scan"], ["unknown"]])
def test_cli_argument_errors_are_handled_by_argparse(args) -> None:
    with pytest.raises(SystemExit):
        cli.main(args)


@pytest.mark.parametrize("timeout", ["0", "nan", "601"])
def test_cli_rejects_unbounded_timeouts(timeout: str) -> None:
    with pytest.raises(SystemExit):
        cli.main(["scan", str(FIXTURES), "--timeout", timeout])


def test_ai_review_requires_explicit_opt_in_and_discloses_single_file_upload(
    monkeypatch, capsys
) -> None:
    from app.core.config import Settings
    from app.domain import Finding, FindingSource, Severity
    import app.infrastructure.ai.factory as ai_factory

    settings = Settings(_env_file=None, environment="test", groq_api_key="mock-key")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    reviewed = {}

    class MockReviewer:
        def __init__(self, _settings):
            pass

        async def review(self, *, file_path, source_code):
            reviewed.update(file_path=file_path, source_code=source_code)
            return [
                Finding(
                    rule_id="AI.TEST.001",
                    source=FindingSource.AI,
                    severity=Severity.LOW,
                    category="Test",
                    message="Mock advisory finding.",
                    file_path=file_path,
                    start_line=1,
                    end_line=1,
                    confidence=50,
                    evidence=source_code.splitlines()[0],
                    suggested_fix="Review manually.",
                )
            ]

    monkeypatch.setattr(ai_factory, "create_ai_reviewer", lambda _settings: MockReviewer(_settings))
    target = FIXTURES / "safe_sample.py"
    status = cli.main(["scan", str(target), "--ai-review", "--format", "json"])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert status == 0
    assert "source file will be sent to Groq" in captured.err
    assert reviewed["source_code"] == target.read_text(encoding="utf-8")
    assert reviewed["file_path"].endswith("safe_sample.py")
    assert report["scan"]["source_uploaded"] is True
    assert report["scan"]["ai_review"]["requested"] is True
    assert report["scan"]["ai_review"]["provider"] == "Groq"
    ai_finding = report["finding_groups"][0]["findings"][0]
    assert ai_finding["source"] == "ai"
    assert ai_finding["analyzer_name"] == "groq-ai-reviewer"


def test_ai_review_uses_configured_huggingface_provider(monkeypatch, capsys) -> None:
    from app.core.config import Settings
    import app.infrastructure.ai.factory as ai_factory

    settings = Settings(
        _env_file=None,
        environment="test",
        ai_provider="huggingface",
        hf_token="mock-token",
        hf_model="openai/gpt-oss-20b",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    reviewed = {}

    class MockReviewer:
        async def review(self, *, file_path, source_code):
            reviewed.update(file_path=file_path, source_code=source_code)
            return []

    monkeypatch.setattr(ai_factory, "create_ai_reviewer", lambda _settings: MockReviewer())
    target = FIXTURES / "safe_sample.py"
    status = cli.main(["scan", str(target), "--ai-review", "--format", "json"])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert status == 0
    assert "sent to Hugging Face" in captured.err
    assert reviewed["source_code"] == target.read_text(encoding="utf-8")
    assert report["scan"]["ai_review"]["provider"] == "Hugging Face"
    assert report["scan"]["ai_review"]["disclosure"] == (
        "One source file was sent to Hugging Face after explicit --ai-review opt-in"
    )


def test_ai_review_refuses_directory_without_loading_provider_config(monkeypatch, capsys, tmp_path):
    def unexpected_settings_load():
        raise AssertionError("directory review must be rejected before loading credentials")

    monkeypatch.setattr(cli, "get_settings", unexpected_settings_load)
    status = cli.main(["scan", str(tmp_path), "--ai-review"])
    captured = capsys.readouterr()

    assert status == 2
    assert "one source file only" in captured.err
