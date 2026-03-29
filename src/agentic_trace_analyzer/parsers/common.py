"""Shared parser helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def event_timestamp(value: str | None) -> datetime | None:
    """Parse ISO-like timestamps from trace records."""
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def flatten_text(parts: Any) -> str | None:
    """Join text fragments while dropping blanks."""
    values = [str(part).strip() for part in parts if part]
    if not values:
        return None
    return "\n".join(values)


def parse_json_lines(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of objects."""
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def parse_json_document(path: Path) -> Any:
    """Load a standard JSON document."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def maybe_json(value: Any) -> Any:
    """Best-effort JSON decode, returning the original value on failure."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value

