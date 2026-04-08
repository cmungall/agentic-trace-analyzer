"""Helpers for loading and querying the failure mode taxonomy."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from agentic_trace_analyzer.schema import SCHEMA_PATH

ROOT_CLASS = "failure_mode"


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Load the raw LinkML schema used as the taxonomy source of truth."""
    with SCHEMA_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@lru_cache(maxsize=1)
def load_ontology() -> dict[str, Any]:
    """Derive a taxonomy view from the strict LinkML class tree."""
    schema = load_schema()
    classes = schema.get("classes", {})
    category_ids = [
        class_name
        for class_name, class_def in classes.items()
        if class_def.get("is_a") == ROOT_CLASS
    ]
    categories = [
        {
            "id": category_id,
            "name": _display_name(classes[category_id], category_id),
            "description": classes[category_id].get("description", ""),
            "category": category_id,
            "subtypes": [
                class_name
                for class_name, class_def in classes.items()
                if (
                    not class_def.get("abstract")
                    and _top_category(class_name, classes) == category_id
                )
            ],
        }
        for category_id in category_ids
    ]
    failure_modes = [
        _failure_mode_entry(class_name, class_def, classes)
        for class_name, class_def in classes.items()
        if _is_leaf_failure_mode(class_name, class_def, classes)
    ]
    return {
        "name": schema.get("title") or schema.get("name"),
        "description": schema.get("description", ""),
        "categories": categories,
        "failure_modes": failure_modes,
    }


@lru_cache(maxsize=1)
def ontology_index() -> dict[str, dict[str, Any]]:
    """Return taxonomy entries indexed by failure mode identifier."""
    ontology = load_ontology()
    return {entry["id"]: entry for entry in ontology.get("failure_modes", [])}


def failure_mode(mode_id: str) -> dict[str, Any]:
    """Fetch a failure mode entry by identifier."""
    index = ontology_index()
    if mode_id not in index:
        raise KeyError(f"Unknown failure mode id: {mode_id}")
    return index[mode_id]


def _failure_mode_entry(
    class_name: str,
    class_def: dict[str, Any],
    classes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    annotations = class_def.get("annotations", {})
    return {
        "id": class_name,
        "name": _display_name(class_def, class_name),
        "description": class_def.get("description", ""),
        "category": _top_category(class_name, classes),
        "severity_range": _annotation_value(annotations, "severity_range") or {},
        "typical_triggers": _annotation_value(annotations, "typical_triggers") or [],
        "detection_signals": _annotation_value(annotations, "detection_signals") or [],
        "mitigations": _annotation_value(annotations, "mitigations") or [],
        "related_failure_modes": _annotation_value(annotations, "related_failure_modes") or [],
        "attributes": class_def.get("attributes", {}),
    }


def _display_name(class_def: dict[str, Any], fallback: str) -> str:
    return class_def.get("title") or fallback.replace("_", " ").title()


def _annotation_value(annotations: dict[str, Any], key: str) -> Any:
    annotation = annotations.get(key)
    if annotation is None:
        return None
    if isinstance(annotation, dict) and "value" in annotation:
        return annotation["value"]
    return annotation


def _is_leaf_failure_mode(
    class_name: str,
    class_def: dict[str, Any],
    classes: dict[str, dict[str, Any]],
) -> bool:
    return not class_def.get("abstract") and _is_descendant_of(class_name, ROOT_CLASS, classes)


def _is_descendant_of(
    class_name: str,
    ancestor_name: str,
    classes: dict[str, dict[str, Any]],
) -> bool:
    current = classes.get(class_name, {})
    while current:
        parent = current.get("is_a")
        if parent is None:
            return False
        if parent == ancestor_name:
            return True
        current = classes.get(parent, {})
    return False


def _top_category(class_name: str, classes: dict[str, dict[str, Any]]) -> str:
    current_name = class_name
    current = classes[current_name]
    while current.get("is_a") and current.get("is_a") != ROOT_CLASS:
        current_name = current["is_a"]
        current = classes[current_name]
    return current_name if current.get("is_a") == ROOT_CLASS else class_name
