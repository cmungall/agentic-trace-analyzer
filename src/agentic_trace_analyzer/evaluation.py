"""Corpus evaluation and agent-review packet helpers."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import shorten
from typing import Any

from agentic_trace_analyzer.classifier import ClassificationReport, classify_session
from agentic_trace_analyzer.corpus import (
    TraceArtifact,
    TraceCorpusManifest,
    load_corpus_manifest,
    resolve_trace_artifact,
)
from agentic_trace_analyzer.models import TraceEvent, TraceSession
from agentic_trace_analyzer.ontology import load_ontology
from agentic_trace_analyzer.parsers import parse_trace_file


@dataclass(slots=True)
class ArtifactEvaluation:
    """Classification and review comparison results for one trace artifact."""

    artifact: TraceArtifact
    resolved_path: Path | None = None
    session: TraceSession | None = None
    report: ClassificationReport | None = None
    status: str = "unreviewed"
    missing_expected: list[str] = field(default_factory=list)
    violated_absent: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the artifact evaluation into a JSON-serializable dict."""
        return {
            "artifact": self.artifact.to_dict(),
            "resolved_path": str(self.resolved_path) if self.resolved_path else None,
            "status": self.status,
            "missing_expected": self.missing_expected,
            "violated_absent": self.violated_absent,
            "error": self.error,
            "classification": self.report.to_dict() if self.report else None,
        }


@dataclass(slots=True)
class CorpusEvaluationReport:
    """Evaluation output for a corpus manifest."""

    manifest: TraceCorpusManifest
    artifacts: list[ArtifactEvaluation] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Return aggregated evaluation counts and error buckets."""
        status_counts = Counter(item.status for item in self.artifacts)
        finding_counts = Counter()
        missing_expected = Counter()
        violated_absent = Counter()

        for item in self.artifacts:
            if item.report:
                for finding in item.report.findings:
                    finding_counts[finding.failure_mode_id] += 1
            for mode_id in item.missing_expected:
                missing_expected[mode_id] += 1
            for mode_id in item.violated_absent:
                violated_absent[mode_id] += 1

        return {
            "artifact_count": len(self.artifacts),
            "evaluated_count": sum(1 for item in self.artifacts if item.report is not None),
            "reviewed_count": sum(1 for item in self.artifacts if item.artifact.has_expectations()),
            "status_counts": dict(status_counts.most_common()),
            "failure_mode_counts": dict(finding_counts.most_common()),
            "missing_expected_counts": dict(missing_expected.most_common()),
            "violated_absent_counts": dict(violated_absent.most_common()),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert the full corpus evaluation into a JSON-serializable dict."""
        return {
            "manifest": self.manifest.to_dict(),
            "summary": self.summary(),
            "artifacts": [item.to_dict() for item in self.artifacts],
        }


def evaluate_manifest(
    manifest_path: Path,
    cache_dir: Path | None = None,
    limit: int | None = None,
) -> CorpusEvaluationReport:
    """Resolve, parse, classify, and compare all artifacts in a manifest."""
    manifest = load_corpus_manifest(manifest_path)
    if cache_dir is not None:
        cache_dir = cache_dir.resolve()

    artifact_evaluations: list[ArtifactEvaluation] = []
    selected_artifacts = manifest.artifacts[:limit] if limit is not None else manifest.artifacts
    for artifact in selected_artifacts:
        try:
            resolved = resolve_trace_artifact(artifact, manifest.source_path, cache_dir=cache_dir)
            session = parse_trace_file(resolved.local_path)
            report = classify_session(session)
            predicted = {finding.failure_mode_id for finding in report.findings}
            missing_expected = sorted(set(artifact.expected_failure_modes) - predicted)
            violated_absent = sorted(set(artifact.expected_absent_failure_modes) & predicted)
            if artifact.has_expectations():
                status = "review_match"
                if missing_expected or violated_absent:
                    status = "review_mismatch"
            else:
                status = "unreviewed"
            artifact_evaluations.append(
                ArtifactEvaluation(
                    artifact=artifact,
                    resolved_path=resolved.local_path,
                    session=session,
                    report=report,
                    status=status,
                    missing_expected=missing_expected,
                    violated_absent=violated_absent,
                )
            )
        except Exception as exc:
            artifact_evaluations.append(
                ArtifactEvaluation(
                    artifact=artifact,
                    status="error",
                    error=str(exc),
                )
            )

    return CorpusEvaluationReport(manifest=manifest, artifacts=artifact_evaluations)


def write_review_packets(
    evaluation: CorpusEvaluationReport,
    output_dir: Path,
    *,
    event_limit: int = 120,
) -> list[Path]:
    """Write compact review packets suitable for agent-assisted annotation."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for item in evaluation.artifacts:
        if item.session is None or item.report is None:
            continue
        packet = build_review_packet(item, event_limit=event_limit)
        path = output_dir / f"{item.artifact.artifact_id}.json"
        path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
        written_paths.append(path)
    return written_paths


def build_review_packet(item: ArtifactEvaluation, *, event_limit: int = 120) -> dict[str, Any]:
    """Build a compact packet for an external agent or reviewer."""
    if item.session is None or item.report is None:
        raise ValueError("Review packets require a parsed session and classification report.")

    ontology = load_ontology()
    allowed_modes = [
        {
            "id": entry["id"],
            "name": entry["name"],
            "category": entry["category"],
            "description": entry["description"],
        }
        for entry in ontology["failure_modes"]
    ]
    return {
        "artifact": item.artifact.to_dict(),
        "task": (
            "Review this trace and return zero or more failure mode findings using only "
            "the allowed failure mode ids. Cite event_ids for every finding."
        ),
        "response_contract": {
            "findings": [
                {
                    "failure_mode_id": "tool_misuse",
                    "confidence": "high",
                    "rationale": "Brief explanation grounded in the trace.",
                    "evidence_event_ids": ["assistant-1", "tool-result-1"],
                }
            ]
        },
        "allowed_failure_modes": allowed_modes,
        "rule_based_findings": [finding.to_dict() for finding in item.report.findings],
        "session_summary": {
            "source": item.session.source,
            "session_id": item.session.session_id,
            "trace_path": str(item.session.trace_path),
            "cwd": item.session.cwd,
            "models": item.session.model_ids,
            "event_count": len(item.session.events),
            "tool_call_count": len(item.session.tool_calls()),
            "error_count": len(item.session.errors()),
        },
        "event_digest": _event_digest(item.session, event_limit=event_limit),
    }


def _event_digest(session: TraceSession, *, event_limit: int) -> dict[str, Any]:
    events = session.events[:event_limit]
    return {
        "event_limit": event_limit,
        "truncated": len(session.events) > event_limit,
        "events": [_event_digest_entry(event) for event in events],
    }


def _event_digest_entry(event: TraceEvent) -> dict[str, Any]:
    entry = {
        "event_id": event.event_id,
        "kind": event.kind,
        "role": event.role,
        "tool_name": event.tool_name,
        "call_id": event.call_id,
        "is_error": event.is_error,
    }
    text = _short_text(event.text)
    tool_output = _short_text(event.tool_output)
    if text:
        entry["text_excerpt"] = text
    if tool_output:
        entry["tool_output_excerpt"] = tool_output
    if event.tool_input is not None:
        entry["tool_input_excerpt"] = _short_text(event.tool_input)
    return entry


def _short_text(value: Any, *, width: int = 280) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    return shorten(" ".join(text.split()), width=width, placeholder="...")
