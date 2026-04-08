import json
import sys
from pathlib import Path

from click.testing import CliRunner

from agentic_trace_analyzer.cli import cli

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_schema_command_dumps_linkml_schema() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["schema"])

    assert result.exit_code == 0
    assert "Agentic Trace Failure Mode Ontology" in result.output
    assert "failure_mode" in result.output
    assert "SeverityLevel" in result.output


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


def test_corpus_eval_command_json_reports_review_matches() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "corpus",
            "eval",
            str(FIXTURES / "corpus_manifest.yaml"),
            "--format",
            "json",
            "--cache-dir",
            str(FIXTURES / ".cache"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["summary"]["artifact_count"] == 3
    assert payload["summary"]["status_counts"]["review_match"] == 3


def test_corpus_adjudicate_command_json_reports_agent_findings(tmp_path: Path) -> None:
    script_path = tmp_path / "mock_adjudicator.py"
    script_path.write_text(
        """
import json
import sys
from pathlib import Path

packet = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
artifact_id = packet["artifact"]["id"]
event_id = packet["event_digest"]["events"][0]["event_id"]
payload = {"findings": []}
if artifact_id == "fixture_codex":
    payload["findings"] = [
        {
            "failure_mode_id": "step_repetition_loop",
            "confidence": "high",
            "rationale": "Repeated tool calls are visible.",
            "evidence_event_ids": [event_id],
        },
        {
            "failure_mode_id": "tool_misuse",
            "confidence": "high",
            "rationale": "The trace shows a tool error.",
            "evidence_event_ids": [event_id],
        },
    ]
elif artifact_id == "fixture_claude":
    payload["findings"] = [
        {
            "failure_mode_id": "tool_misuse",
            "confidence": "high",
            "rationale": "The tool-use error is explicit.",
            "evidence_event_ids": [event_id],
        }
    ]
print(json.dumps(payload))
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "corpus",
            "adjudicate",
            str(FIXTURES / "corpus_manifest.yaml"),
            "--runner",
            "command",
            "--command-template",
            f"{sys.executable} {script_path} {{packet}}",
            "--format",
            "json",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--packet-dir",
            str(tmp_path / "packets"),
            "--adjudication-dir",
            str(tmp_path / "responses"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["summary"]["artifact_count"] == 3
    assert payload["summary"]["status_counts"]["review_match"] == 3
    assert payload["summary"]["agent_failure_mode_counts"]["tool_misuse"] == 2
