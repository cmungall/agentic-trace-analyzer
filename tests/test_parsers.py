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

