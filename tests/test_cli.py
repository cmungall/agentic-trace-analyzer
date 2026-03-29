import json
from pathlib import Path

from click.testing import CliRunner

from agentic_trace_analyzer.cli import cli

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_schema_command_dumps_linkml_schema() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["schema"])

    assert result.exit_code == 0
    assert "Agentic Trace Failure Mode Ontology" in result.output
    assert "FailureCategory" in result.output


def test_analyze_command_reports_findings() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["analyze", str(FIXTURES / "codex_session.jsonl"), "--format", "text"],
    )

    assert result.exit_code == 0
    assert "Session ID: session-123" in result.output
    assert "step_repetition_loop" in result.output
    assert "tool_misuse" in result.output


def test_report_command_json_aggregates_counts() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "report",
            "json",
            "--trace-file",
            str(FIXTURES / "codex_session.jsonl"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["summary"]["trace_count"] == 1
    assert payload["summary"]["failure_mode_counts"]["tool_misuse"] == 1
