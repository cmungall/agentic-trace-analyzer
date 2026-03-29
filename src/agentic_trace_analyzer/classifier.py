"""Rule-based classification of normalized trace sessions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from textwrap import shorten
from typing import Any

from agentic_trace_analyzer.models import TraceEvent, TraceSession
from agentic_trace_analyzer.ontology import failure_mode

DONE_PATTERN = re.compile(
    r"\b(done|complete(?:d)?|finished|resolved|fixed|implemented|all set|wrapped up)\b",
    re.IGNORECASE,
)
VALIDATION_PATTERN = re.compile(
    r"\b("
    r"pytest|test\b|tests\b|ruff check|lint\b|validate|validation|verify|verification|"
    r"just ci|just test|go test|cargo test|npm test|pnpm test"
    r")\b",
    re.IGNORECASE,
)
TOOL_MISUSE_PATTERN = re.compile(
    r"("
    r"schema|validation|jsondecodeerror|missing required|unexpected field|"
    r"invalid argument|invalid args|tool_use_error|traceback"
    r")",
    re.IGNORECASE,
)
DEGRADATION_PATTERN = re.compile(
    r"(fallback|degraded|best effort|reduced toolset|heuristic shortcut)",
    re.IGNORECASE,
)
STATE_DESYNC_PATTERN = re.compile(
    r"("
    r"context_compacted|context compacted|conversation reset|"
    r"loss of conversation history|amnesia|dropped context"
    r")",
    re.IGNORECASE,
)
RESOURCE_PATTERN = re.compile(
    r"("
    r"token limit|token budget|rate limit|quota exceeded|"
    r"insufficient_quota|resource exhausted|out of tokens"
    r")",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ClassificationFinding:
    """A single ontology-backed classification result."""

    failure_mode_id: str
    rationale: str
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the finding into a JSON-serializable dict."""
        ontology_entry = failure_mode(self.failure_mode_id)
        return {
            "failure_mode_id": self.failure_mode_id,
            "name": ontology_entry["name"],
            "category": ontology_entry["category"],
            "severity_range": ontology_entry["severity_range"],
            "rationale": self.rationale,
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class ClassificationReport:
    """Classification output for a single normalized session."""

    session: TraceSession
    findings: list[ClassificationFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the report into a JSON-serializable dict."""
        return {
            "session_id": self.session.session_id,
            "trace_path": str(self.session.trace_path),
            "source": self.session.source,
            "model_ids": self.session.model_ids,
            "finding_count": len(self.findings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def classify_session(session: TraceSession) -> ClassificationReport:
    """Run rule-based failure mode detection against a normalized session."""
    findings: list[ClassificationFinding] = []

    step_repetition = _detect_step_repetition(session)
    if step_repetition:
        findings.append(step_repetition)

    premature_termination = _detect_premature_termination(session)
    if premature_termination:
        findings.append(premature_termination)

    tool_misuse = _detect_tool_misuse(session)
    if tool_misuse:
        findings.append(tool_misuse)

    silent_degradation = _detect_silent_degradation(session)
    if silent_degradation:
        findings.append(silent_degradation)

    state_desync = _detect_state_desync(session)
    if state_desync:
        findings.append(state_desync)

    resource_exhaustion = _detect_resource_exhaustion(session)
    if resource_exhaustion:
        findings.append(resource_exhaustion)

    return ClassificationReport(session=session, findings=findings)


def _detect_step_repetition(session: TraceSession) -> ClassificationFinding | None:
    tool_calls = session.tool_calls()
    if not tool_calls:
        return None

    paired_results = _tool_results_by_call_id(session)
    best_run: list[TraceEvent] = []
    current_run: list[TraceEvent] = []
    current_signature: str | None = None

    for event in tool_calls:
        signature = event.tool_signature()
        if signature and signature == current_signature:
            current_run.append(event)
        else:
            if len(current_run) > len(best_run):
                best_run = current_run
            current_run = [event]
            current_signature = signature

    if len(current_run) > len(best_run):
        best_run = current_run

    if len(best_run) < 2:
        return None

    result_texts = [
        paired_results[event.call_id].tool_output
        for event in best_run
        if event.call_id and event.call_id in paired_results
    ]
    repeated_output = len(set(result_texts)) <= 1 if result_texts else False
    all_errors = all(
        paired_results[event.call_id].is_error
        for event in best_run
        if event.call_id and event.call_id in paired_results
    )
    if len(best_run) < 3 and not (repeated_output or all_errors):
        return None

    signature = best_run[0].tool_signature() or best_run[0].tool_name or "unknown tool"
    display_signature = shorten(signature, width=80, placeholder="...")
    rationale = (
        f"Detected {len(best_run)} repeated calls of `{display_signature}` "
        "without a meaningful state change."
    )
    evidence = [_event_snapshot(event, paired_results.get(event.call_id)) for event in best_run[:5]]
    return ClassificationFinding(
        failure_mode_id="step_repetition_loop",
        rationale=rationale,
        evidence=evidence,
    )


def _detect_premature_termination(session: TraceSession) -> ClassificationFinding | None:
    assistant_messages = [
        event
        for event in session.events
        if event.kind == "message" and event.role == "assistant" and event.text
    ]
    if not assistant_messages:
        return None

    final_message = assistant_messages[-1]
    if not DONE_PATTERN.search(final_message.text or ""):
        return None

    validation_events = [
        event for event in session.events if _looks_like_validation_event(event)
    ]
    if validation_events:
        return None

    rationale = (
        "The trace ends with a completion-style assistant message "
        "but shows no validation step."
    )
    return ClassificationFinding(
        failure_mode_id="premature_termination",
        rationale=rationale,
        evidence=[_event_snapshot(final_message)],
    )


def _detect_tool_misuse(session: TraceSession) -> ClassificationFinding | None:
    matches = []
    for event in session.tool_results():
        searchable = "\n".join(
            filter(None, [_stringify(event.tool_output), _stringify(event.text)])
        )
        if event.is_error and TOOL_MISUSE_PATTERN.search(searchable):
            matches.append(event)

    if not matches:
        return None

    rationale = (
        f"Detected {len(matches)} tool-result errors that match schema or argument misuse patterns."
    )
    return ClassificationFinding(
        failure_mode_id="tool_misuse",
        rationale=rationale,
        evidence=[_event_snapshot(event) for event in matches[:5]],
    )


def _detect_silent_degradation(session: TraceSession) -> ClassificationFinding | None:
    evidence = []
    if len(session.model_ids) > 1:
        evidence.append(
            {
                "type": "model_switch",
                "models": session.model_ids,
            }
        )

    for event in session.events:
        searchable = "\n".join(
            filter(None, [_stringify(event.text), _stringify(event.tool_output)])
        )
        if searchable and DEGRADATION_PATTERN.search(searchable):
            evidence.append(_event_snapshot(event))
            break

    if not evidence:
        return None

    rationale = (
        "The trace shows model or fallback behavior changes "
        "consistent with silent degradation."
    )
    return ClassificationFinding(
        failure_mode_id="weak_fallback_silent_degradation",
        rationale=rationale,
        evidence=evidence[:5],
    )


def _detect_state_desync(session: TraceSession) -> ClassificationFinding | None:
    matches = []
    for event in session.events:
        searchable = "\n".join(
            filter(None, [_stringify(event.text), _stringify(event.tool_output)])
        )
        if searchable and STATE_DESYNC_PATTERN.search(searchable):
            matches.append(event)

    if not matches:
        return None

    rationale = (
        "The trace contains explicit context-loss or reset markers "
        "associated with state desynchronization."
    )
    return ClassificationFinding(
        failure_mode_id="state_desynchronization_context_loss",
        rationale=rationale,
        evidence=[_event_snapshot(event) for event in matches[:5]],
    )


def _detect_resource_exhaustion(session: TraceSession) -> ClassificationFinding | None:
    evidence: list[dict[str, Any]] = []

    for event in session.events:
        if event.kind == "token_count":
            info = event.metadata.get("info") or {}
            total_usage = info.get("total_token_usage") or {}
            total_tokens = total_usage.get("total_tokens")
            context_window = info.get("model_context_window")
            primary_usage = ((event.metadata.get("rate_limits") or {}).get("primary") or {}).get(
                "used_percent"
            )
            if total_tokens and context_window and total_tokens / context_window >= 0.8:
                evidence.append(
                    {
                        "event_id": event.event_id,
                        "kind": event.kind,
                        "context_ratio": round(total_tokens / context_window, 4),
                    }
                )
                break
            if primary_usage is not None and primary_usage >= 80:
                evidence.append(
                    {
                        "event_id": event.event_id,
                        "kind": event.kind,
                        "primary_used_percent": primary_usage,
                    }
                )
                break

        searchable = "\n".join(
            filter(None, [_stringify(event.text), _stringify(event.tool_output)])
        )
        if searchable and RESOURCE_PATTERN.search(searchable):
            evidence.append(_event_snapshot(event))
            break

    if not evidence:
        return None

    rationale = (
        "The trace shows token-budget or quota exhaustion signals "
        "consistent with resource exhaustion."
    )
    return ClassificationFinding(
        failure_mode_id="resource_exhaustion_agent_denial_of_service",
        rationale=rationale,
        evidence=evidence,
    )


def _tool_results_by_call_id(session: TraceSession) -> dict[str, TraceEvent]:
    results: dict[str, TraceEvent] = {}
    for event in session.tool_results():
        if event.call_id and event.call_id not in results:
            results[event.call_id] = event
    return results


def _looks_like_validation_event(event: TraceEvent) -> bool:
    if event.kind != "tool_call":
        return False
    searchable = "\n".join(
        filter(
            None,
            [
                event.tool_name,
                _stringify(event.tool_input),
            ],
        )
    )
    return bool(VALIDATION_PATTERN.search(searchable))


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "\n".join(filter(None, (_stringify(item) for item in value)))
    if isinstance(value, dict):
        return str(value)
    return str(value)


def _event_snapshot(event: TraceEvent, paired_result: TraceEvent | None = None) -> dict[str, Any]:
    snapshot = {
        "event_id": event.event_id,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "kind": event.kind,
        "role": event.role,
        "tool_name": event.tool_name,
        "call_id": event.call_id,
        "is_error": event.is_error,
        "text": event.text,
    }
    if event.tool_input is not None:
        snapshot["tool_input"] = event.tool_input
    if event.tool_output is not None:
        snapshot["tool_output"] = event.tool_output
    if paired_result is not None:
        snapshot["paired_result"] = {
            "event_id": paired_result.event_id,
            "is_error": paired_result.is_error,
            "tool_output": paired_result.tool_output,
        }
    return snapshot
