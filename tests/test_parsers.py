import json
from pathlib import Path

from agentic_trace_analyzer.parsers import parse_trace_file

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_codex_jsonl_fixture() -> None:
    session = parse_trace_file(FIXTURES / "codex_session.jsonl")

    assert session.source == "codex"
    assert session.session_id == "session-123"
    assert session.model_ids == ["gpt-5.2-codex", "gpt-5.2-mini"]
    assert len(session.tool_calls()) == 2
    assert len(session.tool_results()) == 2
    assert len(session.reasoning_events()) == 1
    assert len(session.errors()) == 2


def test_parse_codex_legacy_fixture() -> None:
    session = parse_trace_file(FIXTURES / "codex_legacy.json")

    assert session.source == "codex"
    assert session.session_id == "legacy-456"
    assert len(session.tool_calls()) == 1
    assert len(session.tool_results()) == 1
    assert session.tool_results()[0].tool_output == "diff --git a/file b/file"


def test_parse_claude_jsonl_fixture() -> None:
    session = parse_trace_file(FIXTURES / "claude_session.jsonl")

    assert session.source == "claude"
    assert session.session_id == "claude-789"
    assert session.model_ids == ["claude-sonnet-4-6"]
    assert len(session.tool_calls()) == 1
    assert len(session.tool_results()) == 1
    assert len(session.reasoning_events()) == 1
    assert session.errors()[0].is_error is True


def test_parse_recent_claude_jsonl_with_leading_snapshot(tmp_path: Path) -> None:
    trace_path = tmp_path / "recent-claude.jsonl"
    records = [
        {
            "type": "file-history-snapshot",
            "messageId": "message-1",
            "snapshot": {"timestamp": "2026-03-29T12:00:00Z"},
            "isSnapshotUpdate": False,
        },
        {
            "parentUuid": None,
            "isSidechain": False,
            "type": "user",
            "message": {"role": "user", "content": "1+1"},
            "uuid": "user-1",
            "timestamp": "2026-03-29T12:00:01Z",
            "cwd": "/tmp/claude",
            "sessionId": "claude-recent",
            "version": "2.1.87",
        },
        {
            "parentUuid": "user-1",
            "isSidechain": False,
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-6",
                "id": "msg-1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "2"}],
            },
            "uuid": "assistant-1",
            "timestamp": "2026-03-29T12:00:02Z",
            "cwd": "/tmp/claude",
            "sessionId": "claude-recent",
            "version": "2.1.87",
        },
    ]
    trace_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    session = parse_trace_file(trace_path)

    assert session.source == "claude"
    assert session.session_id == "claude-recent"
    assert session.model_ids == ["claude-sonnet-4-6"]
    assert len(session.events) == 3
