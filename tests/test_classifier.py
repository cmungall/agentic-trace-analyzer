from pathlib import Path

from agentic_trace_analyzer.classifier import classify_session
from agentic_trace_analyzer.parsers import parse_trace_file

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_classifier_detects_requested_failure_modes() -> None:
    session = parse_trace_file(FIXTURES / "codex_session.jsonl")
    report = classify_session(session)

    finding_ids = {finding.failure_mode_id for finding in report.findings}
    assert finding_ids == {
        "step_repetition_loop",
        "premature_termination",
        "tool_misuse",
        "weak_fallback_silent_degradation",
        "state_desynchronization_context_loss",
        "resource_exhaustion_agent_denial_of_service",
    }

