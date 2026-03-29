"""Trace parsers for supported agent session formats."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_trace_analyzer.models import TraceSession

from .claude import parse_claude_trace
from .codex import parse_codex_trace
from .common import parse_json_document, parse_json_lines

SUPPORTED_TRACE_SUFFIXES = {".json", ".jsonl"}


def parse_trace_file(path: str | Path) -> TraceSession:
    """Parse a supported trace file into a normalized session."""
    trace_path = Path(path).expanduser().resolve()
    parser = detect_trace_source(trace_path)
    if parser == "claude":
        return parse_claude_trace(trace_path)
    if parser == "codex":
        return parse_codex_trace(trace_path)
    raise ValueError(f"Unsupported trace file: {trace_path}")


def detect_trace_source(path: Path) -> str:
    """Infer the trace source from the file content."""
    if path.suffix == ".json":
        document = parse_json_document(path)
        if isinstance(document, dict) and {"session", "items"} <= document.keys():
            return "codex"
        raise ValueError(f"Unsupported JSON trace format: {path}")

    first_record = _read_first_record(path)
    if "sessionId" in first_record and (
        {"parentUuid", "message", "type"} <= first_record.keys()
        or first_record.get("type")
        in {"assistant", "user", "progress", "system", "file-history-snapshot", "queue-operation"}
    ):
        return "claude"
    if {"type", "payload"} <= first_record.keys():
        return "codex"
    raise ValueError(f"Could not detect trace source for: {path}")


def discover_trace_files(root: str | Path) -> list[Path]:
    """Discover supported trace files recursively under a directory."""
    root_path = Path(root).expanduser().resolve()
    if root_path.is_file():
        return [root_path]
    files: list[Path] = []
    for path in sorted(root_path.rglob("*")):
        if not path.is_file() or path.suffix not in SUPPORTED_TRACE_SUFFIXES:
            continue
        if path.name.endswith(".meta.json"):
            continue
        try:
            detect_trace_source(path)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        files.append(path)
    return files


def parse_trace_directory(root: str | Path) -> list[TraceSession]:
    """Parse every supported trace file under a directory."""
    return [parse_trace_file(path) for path in discover_trace_files(root)]


def _read_first_record(path: Path) -> dict[str, Any]:
    records = parse_json_lines(path)
    if not records:
        raise ValueError(f"Empty trace file: {path}")
    return records[0]
