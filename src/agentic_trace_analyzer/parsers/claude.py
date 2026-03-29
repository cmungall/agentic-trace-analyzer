"""Parsers for Claude Code JSONL session transcripts."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from agentic_trace_analyzer.models import TraceEvent, TraceSession

from .common import event_timestamp, flatten_text, parse_json_lines


def parse_claude_trace(path: Path) -> TraceSession:
    """Parse a Claude Code JSONL transcript into a normalized session."""
    records = parse_json_lines(path)
    session = TraceSession(source="claude", trace_path=path)

    for index, record in enumerate(records):
        session.session_id = session.session_id or record.get("sessionId")
        session.cwd = session.cwd or record.get("cwd")
        session.cli_version = session.cli_version or record.get("version")

        message = record.get("message") or {}
        session.add_model(message.get("model"))

        record_type = record.get("type")
        if record_type in {"assistant", "user", "system"}:
            _add_message_events(session, record, index)
        elif record_type == "progress":
            data = record.get("data", {})
            event = TraceEvent(
                event_id=f"{path.stem}:{index}",
                timestamp=event_timestamp(record.get("timestamp")),
                kind="lifecycle",
                text=flatten_text([data.get("type"), data.get("hookEvent")]),
                metadata={"record_type": record_type, "data": data},
            )
            session.add_event(event)
        elif record_type in {"file-history-snapshot", "queue-operation"}:
            event = TraceEvent(
                event_id=f"{path.stem}:{index}",
                timestamp=event_timestamp(record.get("timestamp")),
                kind="lifecycle",
                text=record_type,
                metadata={"record_type": record_type},
            )
            session.add_event(event)

    return session


def _add_message_events(session: TraceSession, record: dict[str, Any], index: int) -> None:
    """Extract message, reasoning, tool-call, and tool-result events from Claude records."""
    message = record.get("message") or {}
    role = message.get("role") or record.get("type")
    timestamp = event_timestamp(record.get("timestamp"))
    content = message.get("content")

    if isinstance(content, str):
        event = TraceEvent(
            event_id=f"{session.trace_path.stem}:{index}",
            timestamp=timestamp,
            kind="message",
            role=role,
            text=content,
            model=message.get("model"),
            metadata={"record_type": record.get("type")},
        )
        session.add_event(event)
        return

    if not isinstance(content, Iterable):
        return

    for subindex, item in enumerate(content):
        item_type = item.get("type")
        event_id = f"{session.trace_path.stem}:{index}.{subindex}"
        if item_type == "text":
            session.add_event(
                TraceEvent(
                    event_id=event_id,
                    timestamp=timestamp,
                    kind="message",
                    role=role,
                    text=item.get("text"),
                    model=message.get("model"),
                    metadata={"record_type": record.get("type")},
                )
            )
        elif item_type == "thinking" and item.get("thinking"):
            session.add_event(
                TraceEvent(
                    event_id=event_id,
                    timestamp=timestamp,
                    kind="reasoning",
                    role=role,
                    text=item.get("thinking"),
                    model=message.get("model"),
                    metadata={"record_type": record.get("type")},
                )
            )
        elif item_type == "tool_use":
            session.add_event(
                TraceEvent(
                    event_id=event_id,
                    timestamp=timestamp,
                    kind="tool_call",
                    role=role,
                    model=message.get("model"),
                    tool_name=item.get("name"),
                    tool_input=item.get("input"),
                    call_id=item.get("id"),
                    metadata={"record_type": record.get("type")},
                )
            )
        elif item_type == "tool_result":
            top_level_result = record.get("toolUseResult")
            is_error = bool(item.get("is_error")) or (
                isinstance(top_level_result, str) and top_level_result.lower().startswith("error:")
            )
            session.add_event(
                TraceEvent(
                    event_id=event_id,
                    timestamp=timestamp,
                    kind="tool_result",
                    role=role,
                    tool_output=item.get("content"),
                    call_id=item.get("tool_use_id"),
                    is_error=is_error,
                    metadata={
                        "record_type": record.get("type"),
                        "tool_use_result": top_level_result,
                    },
                )
            )
