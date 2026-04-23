
from agentic_trace_analyzer.ontology import load_ontology
from agentic_trace_analyzer.schema import SCHEMA_PATH


def test_schema_declares_root_tree_and_required_enum() -> None:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "SeverityLevel" in schema_text
    assert "Shah2026FaultDimension" in schema_text
    assert "10.48550/arXiv.2603.06847" in schema_text
    assert "failure_mode:" in schema_text
    assert "tree_root: true" in schema_text


def test_ontology_is_derived_from_class_tree() -> None:
    ontology = load_ontology()
    assert len(ontology["categories"]) == 5

    modes = {entry["id"]: entry for entry in ontology["failure_modes"]}
    weak_fallback = modes["weak_fallback_silent_degradation"]
    for field in [
        "name",
        "description",
        "category",
        "severity_range",
        "typical_triggers",
        "detection_signals",
        "mitigations",
    ]:
        assert field in weak_fallback

    assert "verification_failure" in weak_fallback["related_failure_modes"]
    assert "step_repetition_loop" in {
        subtype
        for category in ontology["categories"]
        if category["id"] == "agent_cognition_orchestration"
        for subtype in category["subtypes"]
    }
    assert "degraded_mode" in weak_fallback["attributes"]
    assert modes["tool_misuse"]["category"] == "tooling_integration_actuation"
