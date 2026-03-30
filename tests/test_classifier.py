from pathlib import Path

from agentic_trace_analyzer.classifier import classify_session
from agentic_trace_analyzer.models import TraceEvent, TraceSession
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


def test_classifier_does_not_treat_prompt_text_or_model_switch_as_degradation() -> None:
    session = TraceSession(
        source="codex",
        trace_path=Path("/tmp/session.jsonl"),
        model_ids=["gpt-5.4", "gpt-5.4-mini"],
        events=[
            TraceEvent(
                event_id="1",
                timestamp=None,
                kind="message",
                role="developer",
                text="Best-effort fetch timeout in seconds when best_effort_fetch=true.",
            ),
            TraceEvent(
                event_id="2",
                timestamp=None,
                kind="message",
                role="assistant",
                text="I am still investigating the repository state.",
            ),
        ],
    )

    report = classify_session(session)

    assert "weak_fallback_silent_degradation" not in {
        finding.failure_mode_id for finding in report.findings
    }


def test_classifier_does_not_treat_best_effort_architecture_discussion_as_degradation() -> None:
    session = TraceSession(
        source="codex",
        trace_path=Path("/tmp/session.jsonl"),
        events=[
            TraceEvent(
                event_id="1",
                timestamp=None,
                kind="message",
                role="assistant",
                text=(
                    "tp needs first-class state transitions, not just best-effort pane "
                    "scraping."
                ),
            ),
        ],
    )

    report = classify_session(session)

    assert "weak_fallback_silent_degradation" not in {
        finding.failure_mode_id for finding in report.findings
    }


def test_classifier_does_not_treat_future_fallback_design_discussion_as_degradation() -> None:
    session = TraceSession(
        source="codex",
        trace_path=Path("/tmp/session.jsonl"),
        events=[
            TraceEvent(
                event_id="1",
                timestamp=None,
                kind="message",
                role="assistant",
                text=(
                    "The clean insertion point is to consult transcript files before "
                    "falling back to pane text."
                ),
            ),
        ],
    )

    report = classify_session(session)

    assert "weak_fallback_silent_degradation" not in {
        finding.failure_mode_id for finding in report.findings
    }


def test_classifier_does_not_treat_shell_failures_as_tool_misuse() -> None:
    session = TraceSession(
        source="codex",
        trace_path=Path("/tmp/session.jsonl"),
        events=[
            TraceEvent(
                event_id="1",
                timestamp=None,
                kind="tool_call",
                tool_name="exec_command",
                tool_input={"cmd": "pytest"},
                call_id="call-1",
            ),
            TraceEvent(
                event_id="2",
                timestamp=None,
                kind="tool_result",
                call_id="call-1",
                tool_output="Exit code: 1\nTraceback (most recent call last):\nValidationError",
                is_error=True,
            ),
        ],
    )

    report = classify_session(session)

    assert "tool_misuse" not in {finding.failure_mode_id for finding in report.findings}
