import json
import sys
from pathlib import Path

from agentic_trace_analyzer.adjudicator import (
    adjudicate_manifest,
    parse_adjudication_response,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_adjudication_response_accepts_nested_result_wrapper() -> None:
    packet = {
        "allowed_failure_modes": [{"id": "tool_misuse"}],
        "event_digest": {"events": [{"event_id": "evt-1"}]},
    }
    raw = json.dumps(
        {
            "result": json.dumps(
                {
                    "findings": [
                        {
                            "failure_mode_id": "tool_misuse",
                            "confidence": "high",
                            "rationale": "The tool error is explicit.",
                            "evidence_event_ids": ["evt-1"],
                        }
                    ]
                }
            )
        }
    )

    findings = parse_adjudication_response(raw, packet)

    assert len(findings) == 1
    assert findings[0].failure_mode_id == "tool_misuse"


def test_parse_adjudication_response_accepts_structured_output_wrapper() -> None:
    packet = {
        "allowed_failure_modes": [{"id": "tool_misuse"}],
        "event_digest": {"events": [{"event_id": "evt-1"}]},
    }
    raw = json.dumps(
        {
            "type": "result",
            "structured_output": {
                "findings": [
                    {
                        "failure_mode_id": "tool_misuse",
                        "confidence": "high",
                        "rationale": "The tool error is explicit.",
                        "evidence_event_ids": ["evt-1"],
                    }
                ]
            },
        }
    )

    findings = parse_adjudication_response(raw, packet)

    assert len(findings) == 1
    assert findings[0].failure_mode_id == "tool_misuse"


def test_adjudicate_manifest_with_command_runner(tmp_path: Path) -> None:
    script_path = tmp_path / "mock_adjudicator.py"
    script_path.write_text(
        """
import json
import sys
from pathlib import Path

packet_path = Path(sys.argv[1])
packet = json.loads(packet_path.read_text(encoding="utf-8"))
artifact_id = packet["artifact"]["id"]
events = [event["event_id"] for event in packet["event_digest"]["events"]]

def first_event():
    return events[0]

payload = {"findings": []}
if artifact_id == "fixture_codex":
    payload["findings"] = [
        {
            "failure_mode_id": "step_repetition_loop",
            "confidence": "high",
            "rationale": "Repeated tool calls are visible.",
            "evidence_event_ids": [first_event()],
        },
        {
            "failure_mode_id": "tool_misuse",
            "confidence": "high",
            "rationale": "The trace shows a tool error.",
            "evidence_event_ids": [first_event()],
        },
    ]
elif artifact_id == "fixture_claude":
    payload["findings"] = [
        {
            "failure_mode_id": "tool_misuse",
            "confidence": "high",
            "rationale": "The tool-use error is explicit.",
            "evidence_event_ids": [first_event()],
        }
    ]

print(json.dumps(payload))
""".strip()
        + "\n",
        encoding="utf-8",
    )

    report = adjudicate_manifest(
        FIXTURES / "corpus_manifest.yaml",
        runner="command",
        command_template=f"{sys.executable} {script_path} {{packet}}",
        cache_dir=tmp_path / "cache",
        packet_dir=tmp_path / "packets",
        adjudication_dir=tmp_path / "responses",
    )

    summary = report.summary()
    assert summary["artifact_count"] == 3
    assert summary["adjudicated_count"] == 3
    assert summary["status_counts"]["review_match"] == 3
    assert summary["agent_failure_mode_counts"]["tool_misuse"] == 2
    assert summary["agent_failure_mode_counts"]["step_repetition_loop"] == 1
    assert summary["rule_only_counts"]["premature_termination"] == 1
    assert (tmp_path / "responses" / "fixture_codex.response.json").exists()
