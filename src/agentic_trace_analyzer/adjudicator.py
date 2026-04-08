"""Agent-assisted trace adjudication over review packets."""

from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentic_trace_analyzer.evaluation import (
    ArtifactEvaluation,
    CorpusEvaluationReport,
    build_review_packet,
    evaluate_manifest,
)

VALID_CONFIDENCE_LEVELS = {"low", "medium", "high"}


@dataclass(slots=True)
class AgentFinding:
    """A single structured finding proposed by an external agent."""

    failure_mode_id: str
    confidence: str
    rationale: str
    evidence_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert the finding into a JSON-serializable dict."""
        return {
            "failure_mode_id": self.failure_mode_id,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "evidence_event_ids": self.evidence_event_ids,
        }


@dataclass(slots=True)
class ArtifactAdjudication:
    """Agent adjudication result for a single artifact."""

    artifact_evaluation: ArtifactEvaluation
    findings: list[AgentFinding] = field(default_factory=list)
    runner_name: str = "unknown"
    packet_path: Path | None = None
    response_path: Path | None = None
    raw_response: str | None = None
    status: str = "unreviewed"
    missing_expected: list[str] = field(default_factory=list)
    violated_absent: list[str] = field(default_factory=list)
    rule_only_failure_modes: list[str] = field(default_factory=list)
    agent_only_failure_modes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the adjudication result into a JSON-serializable dict."""
        return {
            "artifact": self.artifact_evaluation.artifact.to_dict(),
            "runner_name": self.runner_name,
            "packet_path": str(self.packet_path) if self.packet_path else None,
            "response_path": str(self.response_path) if self.response_path else None,
            "status": self.status,
            "missing_expected": self.missing_expected,
            "violated_absent": self.violated_absent,
            "rule_only_failure_modes": self.rule_only_failure_modes,
            "agent_only_failure_modes": self.agent_only_failure_modes,
            "findings": [finding.to_dict() for finding in self.findings],
            "raw_response": self.raw_response,
            "error": self.error,
        }


@dataclass(slots=True)
class CorpusAdjudicationReport:
    """Adjudication results across a corpus manifest."""

    evaluation: CorpusEvaluationReport
    runner_name: str
    artifacts: list[ArtifactAdjudication] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Return aggregate counts for agent findings and mismatches."""
        status_counts = Counter(item.status for item in self.artifacts)
        finding_counts = Counter()
        missing_expected = Counter()
        violated_absent = Counter()
        rule_only_counts = Counter()
        agent_only_counts = Counter()

        for item in self.artifacts:
            for finding in item.findings:
                finding_counts[finding.failure_mode_id] += 1
            for mode_id in item.missing_expected:
                missing_expected[mode_id] += 1
            for mode_id in item.violated_absent:
                violated_absent[mode_id] += 1
            for mode_id in item.rule_only_failure_modes:
                rule_only_counts[mode_id] += 1
            for mode_id in item.agent_only_failure_modes:
                agent_only_counts[mode_id] += 1

        return {
            "artifact_count": len(self.artifacts),
            "adjudicated_count": sum(1 for item in self.artifacts if item.error is None),
            "reviewed_count": sum(
                1
                for item in self.artifacts
                if item.artifact_evaluation.artifact.has_expectations()
            ),
            "status_counts": dict(status_counts.most_common()),
            "agent_failure_mode_counts": dict(finding_counts.most_common()),
            "missing_expected_counts": dict(missing_expected.most_common()),
            "violated_absent_counts": dict(violated_absent.most_common()),
            "rule_only_counts": dict(rule_only_counts.most_common()),
            "agent_only_counts": dict(agent_only_counts.most_common()),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert the adjudication report into a JSON-serializable dict."""
        return {
            "runner_name": self.runner_name,
            "evaluation": self.evaluation.to_dict(),
            "summary": self.summary(),
            "artifacts": [item.to_dict() for item in self.artifacts],
        }


def adjudicate_manifest(
    manifest_path: Path,
    *,
    runner: str,
    cache_dir: Path | None = None,
    limit: int | None = None,
    packet_dir: Path | None = None,
    adjudication_dir: Path | None = None,
    command_template: str | None = None,
    model: str | None = None,
    timeout_seconds: int = 300,
    event_limit: int = 120,
) -> CorpusAdjudicationReport:
    """Evaluate a corpus manifest and run agent adjudication over each trace packet."""
    evaluation = evaluate_manifest(manifest_path, cache_dir=cache_dir, limit=limit)

    with tempfile.TemporaryDirectory(prefix="trace-adjudication-") as temp_root:
        workspace_root = Path(temp_root)
        packet_root = packet_dir.resolve() if packet_dir else workspace_root / "packets"
        response_root = (
            adjudication_dir.resolve() if adjudication_dir else workspace_root / "responses"
        )
        packet_root.mkdir(parents=True, exist_ok=True)
        response_root.mkdir(parents=True, exist_ok=True)

        schema_path = response_root / "adjudication.schema.json"
        schema_path.write_text(
            json.dumps(adjudication_response_schema(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

        adjudications: list[ArtifactAdjudication] = []
        for item in evaluation.artifacts:
            packet_path = packet_root / f"{item.artifact.artifact_id}.packet.json"
            response_path = response_root / f"{item.artifact.artifact_id}.response.json"

            if item.session is None or item.report is None:
                adjudications.append(
                    ArtifactAdjudication(
                        artifact_evaluation=item,
                        runner_name=runner,
                        packet_path=packet_path,
                        response_path=response_path,
                        status="error",
                        error=item.error or "Artifact could not be parsed or classified.",
                    )
                )
                continue

            packet = build_review_packet(item, event_limit=event_limit)
            packet_path.write_text(
                json.dumps(packet, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            try:
                raw_response = _run_adjudicator(
                    runner=runner,
                    packet=packet,
                    packet_path=packet_path,
                    schema_path=schema_path,
                    response_path=response_path,
                    command_template=command_template,
                    model=model,
                    timeout_seconds=timeout_seconds,
                )
                findings = parse_adjudication_response(raw_response, packet)
                response_path.write_text(
                    json.dumps(
                        {"findings": [finding.to_dict() for finding in findings]},
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                adjudications.append(
                    _adjudication_result(
                        item=item,
                        findings=findings,
                        runner_name=runner,
                        packet_path=packet_path,
                        response_path=response_path,
                        raw_response=raw_response,
                    )
                )
            except Exception as exc:
                adjudications.append(
                    ArtifactAdjudication(
                        artifact_evaluation=item,
                        runner_name=runner,
                        packet_path=packet_path,
                        response_path=response_path,
                        status="error",
                        raw_response=response_path.read_text(encoding="utf-8")
                        if response_path.exists()
                        else None,
                        error=str(exc),
                    )
                )

        return CorpusAdjudicationReport(
            evaluation=evaluation,
            runner_name=runner,
            artifacts=adjudications,
        )


def adjudication_response_schema() -> dict[str, Any]:
    """Return the JSON schema enforced on agent adjudication output."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["findings"],
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "failure_mode_id",
                        "confidence",
                        "rationale",
                        "evidence_event_ids",
                    ],
                    "properties": {
                        "failure_mode_id": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": sorted(VALID_CONFIDENCE_LEVELS),
                        },
                        "rationale": {"type": "string"},
                        "evidence_event_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            }
        },
    }


def parse_adjudication_response(raw_response: str, packet: dict[str, Any]) -> list[AgentFinding]:
    """Parse and validate a raw agent response against the review packet."""
    payload = _extract_payload(raw_response)
    findings_raw = payload.get("findings")
    if not isinstance(findings_raw, list):
        raise ValueError("Agent response must contain a `findings` list.")

    allowed_failure_modes = {entry["id"] for entry in packet["allowed_failure_modes"]}
    valid_event_ids = {entry["event_id"] for entry in packet["event_digest"]["events"]}
    findings: list[AgentFinding] = []

    for index, finding_raw in enumerate(findings_raw, start=1):
        if not isinstance(finding_raw, dict):
            raise ValueError(f"Finding #{index} is not an object.")

        failure_mode_id = finding_raw.get("failure_mode_id")
        confidence = finding_raw.get("confidence")
        rationale = finding_raw.get("rationale")
        evidence_event_ids = finding_raw.get("evidence_event_ids")

        if failure_mode_id not in allowed_failure_modes:
            raise ValueError(f"Finding #{index} uses unknown failure_mode_id `{failure_mode_id}`.")
        if confidence not in VALID_CONFIDENCE_LEVELS:
            raise ValueError(f"Finding #{index} has invalid confidence `{confidence}`.")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(f"Finding #{index} requires a non-empty rationale.")
        if not isinstance(evidence_event_ids, list) or not evidence_event_ids:
            raise ValueError(f"Finding #{index} requires at least one evidence_event_id.")
        if not all(isinstance(event_id, str) for event_id in evidence_event_ids):
            raise ValueError(f"Finding #{index} evidence_event_ids must be strings.")

        unknown_event_ids = sorted(set(evidence_event_ids) - valid_event_ids)
        if unknown_event_ids:
            raise ValueError(
                f"Finding #{index} cites unknown event ids: {', '.join(unknown_event_ids)}."
            )

        findings.append(
            AgentFinding(
                failure_mode_id=failure_mode_id,
                confidence=confidence,
                rationale=rationale.strip(),
                evidence_event_ids=list(dict.fromkeys(evidence_event_ids)),
            )
        )

    return findings


def render_adjudication_prompt(packet: dict[str, Any]) -> str:
    """Render the prompt sent to an external agent runner."""
    return (
        "You are reviewing a normalized agent trace packet.\n"
        "Return only JSON that matches the provided schema.\n"
        "Rules:\n"
        "- Use only failure_mode_id values from allowed_failure_modes.\n"
        "- Every finding must cite one or more event ids from event_digest.\n"
        "- If the packet does not support a finding, return an empty findings list.\n"
        "- Do not invent hidden events or missing context.\n\n"
        "Packet JSON:\n"
        f"{json.dumps(packet, indent=2, sort_keys=True)}\n"
    )


def _run_adjudicator(
    *,
    runner: str,
    packet: dict[str, Any],
    packet_path: Path,
    schema_path: Path,
    response_path: Path,
    command_template: str | None,
    model: str | None,
    timeout_seconds: int,
) -> str:
    prompt = render_adjudication_prompt(packet)
    if runner == "codex":
        return _run_codex(prompt, schema_path, response_path, model, timeout_seconds)
    if runner == "claude":
        return _run_claude(prompt, schema_path, model, timeout_seconds)
    if runner == "command":
        if not command_template:
            raise ValueError("The `command` runner requires --command-template.")
        return _run_command_template(
            command_template=command_template,
            prompt=prompt,
            packet_path=packet_path,
            schema_path=schema_path,
            response_path=response_path,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"Unsupported runner `{runner}`.")


def _run_codex(
    prompt: str,
    schema_path: Path,
    response_path: Path,
    model: str | None,
    timeout_seconds: int,
) -> str:
    command = [
        "codex",
        "-a",
        "never",
        "exec",
        "-",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--output-schema",
        str(schema_path),
        "-o",
        str(response_path),
    ]
    if model:
        command[4:4] = ["-m", model]
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Codex adjudicator failed: "
            f"{completed.stderr.strip() or completed.stdout.strip() or completed.returncode}"
        )
    if response_path.exists():
        return response_path.read_text(encoding="utf-8")
    return completed.stdout


def _run_claude(
    prompt: str,
    schema_path: Path,
    model: str | None,
    timeout_seconds: int,
) -> str:
    schema_text = schema_path.read_text(encoding="utf-8")
    command = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--json-schema",
        schema_text,
        "--tools",
        "",
        "--no-session-persistence",
    ]
    if model:
        command.extend(["--model", model])
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Claude adjudicator failed: "
            f"{completed.stderr.strip() or completed.stdout.strip() or completed.returncode}"
        )
    return completed.stdout


def _run_command_template(
    *,
    command_template: str,
    prompt: str,
    packet_path: Path,
    schema_path: Path,
    response_path: Path,
    timeout_seconds: int,
) -> str:
    prompt_path = response_path.with_suffix(".prompt.txt")
    prompt_path.write_text(prompt, encoding="utf-8")
    formatted = command_template.format(
        packet=packet_path,
        schema=schema_path,
        output=response_path,
        prompt=prompt_path,
    )
    completed = subprocess.run(
        shlex.split(formatted),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Command adjudicator failed: "
            f"{completed.stderr.strip() or completed.stdout.strip() or completed.returncode}"
        )
    if response_path.exists():
        return response_path.read_text(encoding="utf-8")
    return completed.stdout


def _extract_payload(raw_response: str) -> dict[str, Any]:
    raw_response = raw_response.strip()
    if not raw_response:
        raise ValueError("Agent response was empty.")

    payload = json.loads(raw_response)
    if isinstance(payload, dict) and "findings" in payload:
        return payload

    if isinstance(payload, dict):
        structured_output = payload.get("structured_output")
        if isinstance(structured_output, dict) and "findings" in structured_output:
            return structured_output

    if isinstance(payload, dict):
        for key in ["result", "content", "text", "output", "last_message"]:
            nested = payload.get(key)
            if isinstance(nested, str):
                nested_payload = _try_parse_nested_json(nested)
                if isinstance(nested_payload, dict) and "findings" in nested_payload:
                    return nested_payload

    raise ValueError("Could not extract an adjudication payload with a `findings` list.")


def _try_parse_nested_json(text: str) -> Any:
    text = text.strip()
    candidates = [text]
    if text.startswith("```"):
        stripped = text.strip("`")
        if "\n" in stripped:
            _, _, rest = stripped.partition("\n")
            candidates.append(rest.rsplit("```", 1)[0].strip())
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _adjudication_result(
    *,
    item: ArtifactEvaluation,
    findings: list[AgentFinding],
    runner_name: str,
    packet_path: Path,
    response_path: Path,
    raw_response: str,
) -> ArtifactAdjudication:
    predicted = {finding.failure_mode_id for finding in findings}
    expected = set(item.artifact.expected_failure_modes)
    absent = set(item.artifact.expected_absent_failure_modes)
    rule_based = {finding.failure_mode_id for finding in item.report.findings}

    missing_expected = sorted(expected - predicted)
    violated_absent = sorted(absent & predicted)
    if item.artifact.has_expectations():
        status = "review_match"
        if missing_expected or violated_absent:
            status = "review_mismatch"
    else:
        status = "unreviewed"

    return ArtifactAdjudication(
        artifact_evaluation=item,
        findings=findings,
        runner_name=runner_name,
        packet_path=packet_path,
        response_path=response_path,
        raw_response=raw_response,
        status=status,
        missing_expected=missing_expected,
        violated_absent=violated_absent,
        rule_only_failure_modes=sorted(rule_based - predicted),
        agent_only_failure_modes=sorted(predicted - rule_based),
    )
