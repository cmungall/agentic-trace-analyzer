
from agentic_trace_analyzer.ontology import load_ontology
from agentic_trace_analyzer.schema import SCHEMA_PATH


def test_schema_declares_required_enums() -> None:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "SeverityLevel" in schema_text
    assert "FailureCategory" in schema_text


def test_ontology_has_six_categories_and_cross_references() -> None:
    ontology = load_ontology()
    assert len(ontology["categories"]) == 6

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
        if category["id"] == "planning_control"
        for subtype in category["subtypes"]
    }

