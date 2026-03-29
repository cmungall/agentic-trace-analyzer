"""Helpers for loading and querying the failure mode ontology."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from agentic_trace_analyzer.schema import ONTOLOGY_PATH


@lru_cache(maxsize=1)
def load_ontology() -> dict[str, Any]:
    """Load the ontology instance data from disk."""
    with ONTOLOGY_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@lru_cache(maxsize=1)
def ontology_index() -> dict[str, dict[str, Any]]:
    """Return ontology entries indexed by failure mode identifier."""
    ontology = load_ontology()
    return {entry["id"]: entry for entry in ontology.get("failure_modes", [])}


def failure_mode(mode_id: str) -> dict[str, Any]:
    """Fetch a failure mode entry by identifier."""
    index = ontology_index()
    if mode_id not in index:
        raise KeyError(f"Unknown failure mode id: {mode_id}")
    return index[mode_id]

