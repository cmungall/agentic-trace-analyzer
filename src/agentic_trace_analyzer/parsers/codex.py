"""Parsers for Codex session exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_trace_analyzer.models import TraceEvent, TraceSession

from .common import event_timestamp, flatten_text, maybe_json, parse_json_document, parse_json_lines


def parse_codex_trace(path: Path) -> TraceSession:
    """Parse a Codex trace from JSONL or legacy JSON exports."""
    if path.suffix == ".json":
        document = parse_json_document(path)
        if isinstance(document, dict) and {"session", "items"} <= document.keys():
            return _parse_legacy_codex_trace(path, document)
        raise ValueError(f"Unsupported Codex JSON format: {path}")
    return _parse_codex_jsonl(path)


def _parse_codex_jsonl(path: Path) -> TraceSession:
    records = parse_json_lines(path)
    session = TraceSession(source="codex", trace_path=path)

    for index, record in enumerate(records):
        record_type = record.get("type")
        payload = record.get("payload") or {}
        timestamp = event_timestamp(record.get("timestamp"))

        if record_type == "session_meta":
            session.session_id = session.session_id or payload.get("id")
            session.cwd = session.cwd or payload.get("cwd")
            session.cli_version = session.cli_version or payload.get("cli_version")
            session.metadata["session_meta"] = payload
            continue

        if record_type == "turn_context":
            session.cwd = session.cwd or payload.get("cwd")
            session.add_model(payload.get("model"))
            session.add_event(
                TraceEvent(
                    event_id=f"{path.stem}:{index}",
                    timestamp=timestamp,
                    kind="context",
                    model=payload.get("model"),
                    text=payload.get("summary"),
                    metadata={"record_type": record_type, "payload": payload},
                )
            )
            continue

        if record_type == "response_item":
            _add_response_item(session, path, index, timestamp, payload)
            continue

        if record_type == "event_msg":
            _add_event_msg(session, path, index, timestamp, payload)
            continue

        if record_type == "compacted":
            session.add_event(
                TraceEvent(
                    event_id=f"{path.stem}:{index}",
                    timestamp=timestamp,
                    kind="lifecycle",
                    text="context_compacted",
                    metadata={"record_type": record_type, "payload": payload},
                )
            )

    return session


def _parse_legacy_codex_trace(path: Path, document: dict[str, Any]) -> TraceSession:
    session_meta = document.get("session") or {}
    session = TraceSession(
        source="codex",
        trace_path=path,
        session_id=session_meta.get("id"),
        cwd=session_meta.get("cwd"),
        cli_version=session_meta.get("cli_version"),
        metadata={"session_meta": session_meta},
    )

    for index, item in enumerate(document.get("items") or []):
        item_type = item.get("type")
        timestamp = event_timestamp(item.get("timestamp") or session_meta.get("timestamp"))
        if item_type == "message":
            session.add_event(
                TraceEvent(
                    event_id=f"{path.stem}:{index}",
                    timestamp=timestamp,
                    kind="message",
                    role=item.get("role"),
                    text=_extract_codex_message_text(item.get("content") or []),
                    metadata={"record_type": item_type},
                )
            )
        elif item_type == "reasoning":
            summary = flatten_text(entry.get("text") for entry in item.get("summary") or [])
            session.add_event(
                TraceEvent(
                    event_id=f"{path.stem}:{index}",
                    timestamp=timestamp,
                    kind="reasoning",
                    text=summary,
                    metadata={"record_type": item_type, "duration_ms": item.get("duration_ms")},
                )
            )
        elif item_type == "local_shell_call":
            action = item.get("action") or {}
            session.add_event(
                TraceEvent(
                    event_id=f"{path.stem}:{index}",
                    timestamp=timestamp,
                    kind="tool_call",
                    tool_name="shell_command",
                    tool_input={
                        "command": action.get("command"),
                        "working_directory": action.get("working_directory"),
                        "timeout_ms": action.get("timeout_ms"),
                    },
                    call_id=item.get("call_id"),
                    metadata={"record_type": item_type, "status": item.get("status")},
                )
            )
        elif item_type == "local_shell_call_output":
            output_payload = maybe_json(item.get("output"))
            metadata = (
                output_payload.get("metadata", {})
                if isinstance(output_payload, dict)
                else {}
            )
            tool_output = (
                output_payload.get("output")
                if isinstance(output_payload, dict)
                else item.get("output")
            )
            session.add_event(
                TraceEvent(
                    event_id=f"{path.stem}:{index}",
                    timestamp=timestamp,
                    kind="tool_result",
                    call_id=item.get("call_id"),
                    tool_output=tool_output,
                    is_error=bool(metadata.get("exit_code")),
                    metadata={"record_type": item_type, **metadata},
                )
            )

    return session


def _add_response_item(
    session: TraceSession,
    path: Path,
    index: int,
    timestamp,
    payload: dict[str, Any],
) -> None:
    payload_type = payload.get("type")
    event_id = f"{path.stem}:{index}"

    if payload_type == "message":
        session.add_event(
            TraceEvent(
                event_id=event_id,
                timestamp=timestamp,
                kind="message",
                role=payload.get("role"),
                text=_extract_codex_message_text(payload.get("content") or []),
                metadata={"payload_type": payload_type},
            )
        )
    elif payload_type == "reasoning":
        summary = flatten_text(entry.get("text") for entry in payload.get("summary") or [])
        session.add_event(
            TraceEvent(
                event_id=event_id,
                timestamp=timestamp,
                kind="reasoning",
                text=summary,
                metadata={"payload_type": payload_type},
            )
        )
    elif payload_type in {"function_call", "custom_tool_call"}:
        tool_input = payload.get("input")
        if tool_input is None and payload.get("arguments") is not None:
            tool_input = maybe_json(payload.get("arguments"))
        session.add_event(
            TraceEvent(
                event_id=event_id,
                timestamp=timestamp,
                kind="tool_call",
                tool_name=payload.get("name"),
                tool_input=tool_input,
                call_id=payload.get("call_id"),
                metadata={"payload_type": payload_type, "status": payload.get("status")},
            )
        )
    elif payload_type in {"function_call_output", "custom_tool_call_output"}:
        raw_output = payload.get("output")
        parsed_output = maybe_json(raw_output)
        metadata = parsed_output.get("metadata", {}) if isinstance(parsed_output, dict) else {}
        tool_output = parsed_output.get("output") if isinstance(parsed_output, dict) else raw_output
        exit_code = metadata.get("exit_code")
        session.add_event(
            TraceEvent(
                event_id=event_id,
                timestamp=timestamp,
                kind="tool_result",
                call_id=payload.get("call_id"),
                tool_output=tool_output,
                is_error=bool(exit_code) or _looks_like_failure(tool_output),
                metadata={"payload_type": payload_type, **metadata},
            )
        )


def _add_event_msg(
    session: TraceSession,
    path: Path,
    index: int,
    timestamp,
    payload: dict[str, Any],
) -> None:
    payload_type = payload.get("type")
    event_id = f"{path.stem}:{index}"

    if payload_type == "agent_reasoning":
        session.add_event(
            TraceEvent(
                event_id=event_id,
                timestamp=timestamp,
                kind="reasoning",
                role="assistant",
                text=payload.get("text"),
                metadata={"payload_type": payload_type},
            )
        )
    elif payload_type == "token_count":
        session.add_event(
            TraceEvent(
                event_id=event_id,
                timestamp=timestamp,
                kind="token_count",
                text=None,
                metadata={"payload_type": payload_type, **payload},
            )
        )
    elif payload_type in {"turn_aborted", "context_compacted"}:
        session.add_event(
            TraceEvent(
                event_id=event_id,
                timestamp=timestamp,
                kind="lifecycle",
                text=payload_type,
                is_error=payload_type == "turn_aborted",
                metadata={"payload_type": payload_type, **payload},
            )
        )


def _extract_codex_message_text(content: list[dict[str, Any]]) -> str | None:
    return flatten_text(item.get("text") for item in content if isinstance(item, dict))


def _looks_like_failure(output: Any) -> bool:
    if not isinstance(output, str):
        return False
    lowered = output.lower()
    return lowered.startswith("error:") or "exit code: 1" in lowered or "traceback" in lowered
