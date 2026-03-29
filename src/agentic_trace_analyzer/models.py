"""Normalized trace models shared by parsers, classifiers, and the CLI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def stable_serialize(value: Any) -> str:
    """Serialize arbitrary values into a stable string form."""
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)


@dataclass(slots=True)
class TraceEvent:
    """A normalized event extracted from a trace transcript."""

    event_id: str
    timestamp: datetime | None
    kind: str
    role: str | None = None
    text: str | None = None
    model: str | None = None
    tool_name: str | None = None
    tool_input: Any = None
    tool_output: str | None = None
    call_id: str | None = None
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def tool_signature(self) -> str | None:
        """Return a stable signature for tool repetition detection."""
        if not self.tool_name:
            return None
        return f"{self.tool_name}:{stable_serialize(self.tool_input)}"

    def to_dict(self) -> dict[str, Any]:
        """Convert the event into a JSON-serializable dict."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "kind": self.kind,
            "role": self.role,
            "text": self.text,
            "model": self.model,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "call_id": self.call_id,
            "is_error": self.is_error,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class TraceSession:
    """A normalized session composed of trace events."""

    source: str
    trace_path: Path
    session_id: str | None = None
    cwd: str | None = None
    cli_version: str | None = None
    model_ids: list[str] = field(default_factory=list)
    events: list[TraceEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_model(self, model: str | None) -> None:
        """Track models observed in the session while preserving order."""
        if model and model not in self.model_ids:
            self.model_ids.append(model)

    def add_event(self, event: TraceEvent) -> None:
        """Append an event and harvest any model identifier on it."""
        self.events.append(event)
        self.add_model(event.model)

    def tool_calls(self) -> list[TraceEvent]:
        """Return all normalized tool-call events."""
        return [event for event in self.events if event.kind == "tool_call"]

    def tool_results(self) -> list[TraceEvent]:
        """Return all normalized tool-result events."""
        return [event for event in self.events if event.kind == "tool_result"]

    def reasoning_events(self) -> list[TraceEvent]:
        """Return all reasoning events with extracted text."""
        return [event for event in self.events if event.kind == "reasoning"]

    def errors(self) -> list[TraceEvent]:
        """Return all events flagged as errors."""
        return [event for event in self.events if event.is_error]

    def to_dict(self) -> dict[str, Any]:
        """Convert the session into a JSON-serializable dict."""
        return {
            "source": self.source,
            "trace_path": str(self.trace_path),
            "session_id": self.session_id,
            "cwd": self.cwd,
            "cli_version": self.cli_version,
            "model_ids": self.model_ids,
            "event_count": len(self.events),
            "events": [event.to_dict() for event in self.events],
            "metadata": self.metadata,
        }

