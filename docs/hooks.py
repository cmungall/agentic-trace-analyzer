"""Generate MkDocs reference pages from the LinkML taxonomy schema."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agentic_trace_analyzer.ontology import load_ontology  # noqa: E402

SCHEMA_PATH = (
    ROOT / "src" / "agentic_trace_analyzer" / "schema" / "failure_modes.linkml.yaml"
)
REFERENCE_DIR = ROOT / "docs" / "reference"
ROOT_CLASS = "failure_mode"


def on_pre_build(*, config: Any) -> None:
    """Render generated schema and taxonomy docs before MkDocs builds the site."""
    del config
    schema = _load_yaml(SCHEMA_PATH)
    ontology = load_ontology()
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    _write_if_changed(REFERENCE_DIR / "index.md", _render_reference_index(schema, ontology))
    _write_if_changed(REFERENCE_DIR / "classes.md", _render_classes_page(schema))
    _write_if_changed(REFERENCE_DIR / "slots.md", _render_slots_page(schema))
    _write_if_changed(REFERENCE_DIR / "enums.md", _render_enums_page(schema))
    _write_if_changed(
        REFERENCE_DIR / "failure-modes.md",
        _render_failure_modes_page(schema, ontology),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _write_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


def _render_reference_index(schema: dict[str, Any], ontology: dict[str, Any]) -> str:
    classes = schema.get("classes", {})
    slots = schema.get("slots", {})
    enums = schema.get("enums", {})
    categories = ontology.get("categories", [])
    failure_modes = ontology.get("failure_modes", [])
    schema_annotations = _normalize_annotations(schema.get("annotations", {}))
    reference_lines = [
        f"- Primary reference: {schema_annotations['primary_reference']}"
        for key in ["primary_reference"]
        if key in schema_annotations
    ]
    if "primary_reference_url" in schema_annotations:
        reference_lines.append(
            f"- Primary source URL: <{schema_annotations['primary_reference_url']}>"
        )
    if "primary_reference_doi" in schema_annotations:
        reference_lines.append(f"- DOI: `{schema_annotations['primary_reference_doi']}`")
    if "alignment_note" in schema_annotations:
        reference_lines.append(f"- Alignment: {schema_annotations['alignment_note']}")
    for note in schema_annotations.get("local_extension_note", []):
        reference_lines.append(f"- Local extension note: {note}")
    return "\n".join(
        [
            "# LinkML Reference",
            "",
            "This section is generated from the LinkML schema, which now models the",
            "taxonomy directly as a strict class tree.",
            "",
            "## Source File",
            "",
            f"- Schema: `{SCHEMA_PATH.relative_to(ROOT)}`",
            "",
            "## Taxonomy Alignment",
            "",
            *reference_lines,
            "",
            "## Schema Stats",
            "",
            "| Item | Count |",
            "| --- | ---: |",
            f"| Taxonomy classes | {len(classes)} |",
            f"| Global slots | {len(slots)} |",
            f"| Enums | {len(enums)} |",
            f"| Top-level categories | {len(categories)} |",
            f"| Concrete failure modes | {len(failure_modes)} |",
            "",
            "## Contents",
            "",
            "<div class=\"grid cards\" markdown>",
            "",
            "-   __Classes__",
            "",
            "    ---",
            "",
            "    The strict taxonomy tree, including abstract categories and leaf modes.",
            "",
            "    [Open classes](classes.md)",
            "",
            "-   __Enums__",
            "",
            "    ---",
            "",
            "    Shared schema enums including `SeverityLevel` and the Shah et al. reference vocabularies.",
            "",
            "    [Open enums](enums.md)",
            "",
            "-   __Failure Modes__",
            "",
            "    ---",
            "",
            "    A generated catalog of leaf modes grouped by category.",
            "",
            "    [Open failure modes](failure-modes.md)",
            "",
            "-   __Slots__",
            "",
            "    ---",
            "",
            "    Global slots, if any, defined outside individual classes.",
            "",
            "    [Open slots](slots.md)",
            "",
            "</div>",
        ]
    ) + "\n"


def _render_classes_page(schema: dict[str, Any]) -> str:
    classes = schema.get("classes", {})
    parts = [
        "# Classes",
        "",
        "Generated from the LinkML schema.",
        "",
        "The taxonomy is modeled directly in the class hierarchy:",
        "",
        f"- `{ROOT_CLASS}` is the abstract root",
        "- abstract direct children are top-level categories",
        "- non-abstract descendants are concrete failure modes",
        "",
    ]
    for class_name, class_def in classes.items():
        parts.extend(
            [
                f"## `{class_name}`",
                "",
                class_def.get("description", "No description."),
                "",
                "| Property | Value |",
                "| --- | --- |",
                f"| Title | {_escape_cell(class_def.get('title', ''))} |",
                f"| Abstract | {_bool_label(class_def.get('abstract')) or 'No'} |",
                (
                    f"| Parent | `{class_def.get('is_a', '')}` |"
                    if class_def.get("is_a")
                    else "| Parent |  |"
                ),
                "",
            ]
        )
        parts.extend(_render_mapping_section(class_def))
        attributes = class_def.get("attributes", {})
        if attributes:
            parts.extend(
                [
                    "### Attributes",
                    "",
                    "| Attribute | Range | Description |",
                    "| --- | --- | --- |",
                ]
            )
            for attr_name, attr_def in attributes.items():
                parts.append(
                    "| "
                    f"`{attr_name}` | `{attr_def.get('range', 'string')}` | "
                    f"{_escape_cell(attr_def.get('description', ''))} |"
                )
            parts.append("")
        annotations = class_def.get("annotations", {})
        if annotations:
            parts.extend(
                [
                    "### Taxonomy Metadata",
                    "",
                    "- Severity range: "
                    f"{_render_severity_range(annotations.get('severity_range'))}",
                ]
            )
            parts.extend(
                _render_annotation_list("Typical triggers", annotations, "typical_triggers")
            )
            parts.extend(
                _render_annotation_list("Detection signals", annotations, "detection_signals")
            )
            parts.extend(_render_annotation_list("Mitigations", annotations, "mitigations"))
            parts.extend(
                _render_annotation_list(
                    "Related failure modes",
                    annotations,
                    "related_failure_modes",
                    wrap_code=True,
                )
            )
            parts.extend(
                _render_metadata_table(
                    "Additional Metadata",
                    _extra_annotations(
                        annotations,
                        excluded={
                            "severity_range",
                            "typical_triggers",
                            "detection_signals",
                            "mitigations",
                            "related_failure_modes",
                        },
                    ),
                )
            )
    return "\n".join(parts) + "\n"


def _render_slots_page(schema: dict[str, Any]) -> str:
    slots = schema.get("slots", {})
    parts = [
        "# Slots",
        "",
        "Generated from the LinkML schema.",
        "",
    ]
    if not slots:
        parts.extend(
            [
                "This schema intentionally keeps the taxonomy in the class tree and",
                "uses leaf-class attributes for failure-mode-specific fields, so there",
                "are currently no global slots.",
                "",
            ]
        )
        return "\n".join(parts) + "\n"

    parts.extend(
        [
            "| Slot | Range | Required | Multivalued | Inline | Description |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for slot_name, slot_def in slots.items():
        parts.append(
            "| "
            f"`{slot_name}` | `{slot_def.get('range', 'string')}` | "
            f"{_bool_label(slot_def.get('required'))} | "
            f"{_bool_label(slot_def.get('multivalued'))} | "
            f"{_bool_label(slot_def.get('inlined') or slot_def.get('inlined_as_list'))} | "
            f"{_escape_cell(slot_def.get('description', ''))} |"
        )
    parts.append("")
    return "\n".join(parts) + "\n"


def _render_enums_page(schema: dict[str, Any]) -> str:
    parts = [
        "# Enums",
        "",
        "Generated from the LinkML schema.",
        "",
    ]
    for enum_name, enum_def in schema.get("enums", {}).items():
        parts.extend(
            [
                f"## `{enum_name}`",
                "",
                enum_def.get("description", "No description."),
                "",
            ]
        )
        parts.extend(
            _render_metadata_table(
                "Metadata",
                _normalize_annotations(enum_def.get("annotations", {})),
            )
        )
        parts.extend(
            [
                "| Permissible value | Display text | Description | Metadata |",
                "| --- | --- | --- | --- |",
            ]
        )
        for value_name, value_def in enum_def.get("permissible_values", {}).items():
            parts.append(
                "| "
                f"`{value_name}` | {value_def.get('text', '')} | "
                f"{_escape_cell(value_def.get('description', ''))} | "
                f"{_format_metadata_value(_normalize_annotations(value_def.get('annotations', {})))} |"
            )
        parts.append("")
    return "\n".join(parts) + "\n"


def _render_failure_modes_page(schema: dict[str, Any], ontology: dict[str, Any]) -> str:
    classes = schema.get("classes", {})
    category_names = {
        category["id"]: category["name"] for category in ontology.get("categories", [])
    }
    grouped: dict[str, list[dict[str, Any]]] = {
        category["id"]: [] for category in ontology.get("categories", [])
    }
    for mode in ontology.get("failure_modes", []):
        grouped.setdefault(mode["category"], []).append(mode)

    parts = [
        "# Failure Modes",
        "",
        "Generated from the strict class taxonomy.",
        "",
    ]
    for category in ontology.get("categories", []):
        category_id = category["id"]
        parts.extend(
            [
                f"## {category['name']}",
                "",
                category.get("description", ""),
                "",
            ]
        )
        for mode in grouped.get(category_id, []):
            class_def = classes.get(mode["id"], {})
            severity = mode.get("severity_range", {})
            mapping_text = _format_mapping_cell(class_def)
            parts.extend(
                [
                    f"### `{mode['id']}`",
                    "",
                    f"**{mode['name']}**",
                    "",
                    mode.get("description", ""),
                    "",
                    "| Field | Value |",
                    "| --- | --- |",
                    f"| Category | {category_names.get(mode['category'], mode['category'])} |",
                    "| Severity range | "
                    f"`{severity.get('minimum', '?')}` -> "
                    f"`{severity.get('maximum', '?')}` |",
                ]
            )
            if mapping_text:
                parts.append(f"| Mappings | {mapping_text} |")
            parts.append("")
            parts.extend(
                _render_metadata_table(
                    "Alignment Metadata",
                    _extra_annotations(
                        class_def.get("annotations", {}),
                        excluded={
                            "severity_range",
                            "typical_triggers",
                            "detection_signals",
                            "mitigations",
                            "related_failure_modes",
                        },
                    ),
                )
            )
            parts.extend(_render_list_section("Typical triggers", mode.get("typical_triggers", [])))
            parts.extend(
                _render_list_section("Detection signals", mode.get("detection_signals", []))
            )
            parts.extend(_render_list_section("Mitigations", mode.get("mitigations", [])))
            related = [f"`{value}`" for value in mode.get("related_failure_modes", [])]
            parts.extend(_render_list_section("Related failure modes", related))
            attributes = mode.get("attributes", {})
            if attributes:
                parts.extend(
                    [
                        "#### Failure-specific attributes",
                        "",
                        "| Attribute | Range | Description |",
                        "| --- | --- | --- |",
                    ]
                )
                for attr_name, attr_def in attributes.items():
                    parts.append(
                        "| "
                        f"`{attr_name}` | `{attr_def.get('range', 'string')}` | "
                        f"{_escape_cell(attr_def.get('description', ''))} |"
                    )
                parts.append("")
    return "\n".join(parts) + "\n"


def _render_annotation_list(
    title: str,
    annotations: dict[str, Any],
    key: str,
    *,
    wrap_code: bool = False,
) -> list[str]:
    values = _annotation_value(annotations.get(key)) or []
    if not values:
        return []
    lines = [f"- {title}:"]
    for value in values:
        item = f"`{value}`" if wrap_code else str(value)
        lines.append(f"  - {item}")
    lines.append("")
    return lines


def _render_list_section(title: str, values: list[str]) -> list[str]:
    if not values:
        return []
    lines = [f"#### {title}", ""]
    lines.extend(f"- {value}" for value in values)
    lines.append("")
    return lines


def _render_severity_range(annotation: Any) -> str:
    value = _annotation_value(annotation) or {}
    return f"`{value.get('minimum', '?')}` -> `{value.get('maximum', '?')}`"


def _annotation_value(annotation: Any) -> Any:
    if isinstance(annotation, dict) and "value" in annotation:
        return annotation["value"]
    return annotation


def _normalize_annotations(annotations: dict[str, Any]) -> dict[str, Any]:
    return {key: _annotation_value(value) for key, value in annotations.items()}


def _extra_annotations(
    annotations: dict[str, Any],
    *,
    excluded: set[str],
) -> dict[str, Any]:
    normalized = _normalize_annotations(annotations)
    return {key: value for key, value in normalized.items() if key not in excluded}


def _render_mapping_section(definition: dict[str, Any]) -> list[str]:
    mapping_text = _format_mapping_cell(definition)
    if not mapping_text:
        return []
    return [
        "### Mappings",
        "",
        f"- {mapping_text}",
        "",
    ]


def _format_mapping_cell(definition: dict[str, Any]) -> str:
    labels = {
        "exact_mappings": "Exact",
        "close_mappings": "Close",
        "broad_mappings": "Broad",
        "narrow_mappings": "Narrow",
        "related_mappings": "Related",
    }
    rendered: list[str] = []
    for key, label in labels.items():
        values = definition.get(key, [])
        if values:
            rendered.append(f"{label}: " + ", ".join(f"`{value}`" for value in values))
    return "<br>".join(rendered)


def _render_metadata_table(title: str, metadata: dict[str, Any]) -> list[str]:
    if not metadata:
        return []
    lines = [
        f"### {title}",
        "",
        "| Key | Value |",
        "| --- | --- |",
    ]
    for key, value in metadata.items():
        lines.append(f"| `{key}` | {_format_metadata_value(value)} |")
    lines.append("")
    return lines


def _format_metadata_value(value: Any) -> str:
    if isinstance(value, dict):
        return "<br>".join(
            f"`{key}`: {_format_metadata_value(inner_value)}"
            for key, inner_value in value.items()
        )
    if isinstance(value, list):
        return "<br>".join(str(item) for item in value)
    if value is None:
        return ""
    return _escape_cell(str(value))


def _bool_label(value: Any) -> str:
    return "Yes" if value else ""


def _escape_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
