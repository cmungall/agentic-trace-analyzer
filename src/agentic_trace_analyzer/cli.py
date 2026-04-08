"""Click entrypoint for the agentic trace analyzer."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import click

from agentic_trace_analyzer.adjudicator import adjudicate_manifest
from agentic_trace_analyzer.classifier import ClassificationReport, classify_session
from agentic_trace_analyzer.corpus import load_corpus_manifest, summarize_manifest
from agentic_trace_analyzer.evaluation import evaluate_manifest, write_review_packets
from agentic_trace_analyzer.ontology import load_ontology
from agentic_trace_analyzer.parsers import (
    discover_trace_files,
    parse_trace_file,
)
from agentic_trace_analyzer.schema import SCHEMA_PATH

DEFAULT_SESSION_DIRS = [
    Path.home() / ".codex" / "sessions",
    Path.home() / ".claude" / "projects",
]


@click.group(help="Analyze and classify agentic session traces.")
def cli() -> None:
    """Top-level CLI group."""


@cli.command("analyze")
@click.argument("trace_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    show_default=True,
)
@click.option("--classify/--no-classify", default=True, show_default=True)
def analyze_command(trace_file: Path, output_format: str, classify: bool) -> None:
    """Parse and summarize a single trace file."""
    session = parse_trace_file(trace_file)
    report = classify_session(session) if classify else None
    payload = {
        "session": session.to_dict(),
        "classification": report.to_dict() if report else None,
    }
    click.echo(_render_single_session(session, report, output_format, payload))


@cli.command("classify")
@click.argument("session_dir", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    show_default=True,
)
@click.option("--limit", type=int, default=None)
def classify_command(session_dir: Path, output_format: str, limit: int | None) -> None:
    """Classify every supported trace file under a session directory."""
    trace_files = discover_trace_files(session_dir)
    if limit is not None:
        trace_files = trace_files[:limit]
    sessions = [parse_trace_file(trace_file) for trace_file in trace_files]
    reports = [classify_session(session) for session in sessions]
    payload = {
        "reports": [report.to_dict() for report in reports],
        "summary": _aggregate_reports(reports),
    }
    click.echo(_render_reports(reports, output_format, payload))


@cli.command("report")
@click.argument("output_format", type=click.Choice(["text", "json", "markdown"]))
@click.option(
    "--session-dir",
    "session_dirs",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="One or more directories of trace files. Defaults to Codex and Claude homes.",
)
@click.option(
    "--trace-file",
    "trace_files",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Specific trace files to include in the aggregate report.",
)
@click.option("--limit", type=int, default=None, help="Maximum number of traces to analyze.")
def report_command(
    output_format: str,
    session_dirs: tuple[Path, ...],
    trace_files: tuple[Path, ...],
    limit: int | None,
) -> None:
    """Generate an aggregate report across one or more traces or session directories."""
    sessions = _load_report_sessions(session_dirs, trace_files, limit)
    reports = [classify_session(session) for session in sessions]
    payload = {
        "reports": [report.to_dict() for report in reports],
        "summary": _aggregate_reports(reports),
    }
    click.echo(_render_aggregate_report(reports, output_format, payload))


@cli.command("schema")
@click.option("--include-data/--schema-only", default=False, show_default=True)
def schema_command(include_data: bool) -> None:
    """Dump the LinkML schema, optionally followed by ontology instance data."""
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    if not include_data:
        click.echo(schema_text.rstrip())
        return

    ontology_text = json.dumps(load_ontology(), indent=2, sort_keys=True)
    click.echo(schema_text.rstrip())
    click.echo("\n# Ontology Data")
    click.echo(ontology_text)


@cli.group("corpus", help="Validate and evaluate trace corpus manifests.")
def corpus_group() -> None:
    """Corpus manifest subcommands."""


@corpus_group.command("validate")
@click.argument("manifest", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    show_default=True,
)
def corpus_validate_command(manifest: Path, output_format: str) -> None:
    """Validate a trace corpus manifest and summarize its coverage."""
    corpus_manifest = load_corpus_manifest(manifest)
    summary = summarize_manifest(corpus_manifest)
    payload = {
        "manifest": corpus_manifest.to_dict(),
        "summary": summary,
    }
    click.echo(_render_corpus_manifest(corpus_manifest, summary, output_format, payload))


@corpus_group.command("eval")
@click.argument("manifest", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    show_default=True,
)
@click.option("--limit", type=int, default=None)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=Path(".cache/trace-corpus"),
    show_default=True,
)
@click.option(
    "--emit-review-packets",
    type=click.Path(path_type=Path),
    default=None,
    help="Write compact JSON packets for agent-assisted review.",
)
def corpus_eval_command(
    manifest: Path,
    output_format: str,
    limit: int | None,
    cache_dir: Path,
    emit_review_packets: Path | None,
) -> None:
    """Evaluate classifier output against a trace corpus manifest."""
    evaluation = evaluate_manifest(manifest, cache_dir=cache_dir, limit=limit)
    written_packets = (
        write_review_packets(evaluation, emit_review_packets) if emit_review_packets else []
    )
    payload = evaluation.to_dict()
    if written_packets:
        payload["review_packets"] = [str(path) for path in written_packets]
    click.echo(_render_corpus_evaluation(evaluation, output_format, payload, written_packets))


@corpus_group.command("adjudicate")
@click.argument("manifest", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--runner",
    type=click.Choice(["codex", "claude", "command"]),
    default="codex",
    show_default=True,
)
@click.option(
    "--command-template",
    default=None,
    help=(
        "Command template for the `command` runner. "
        "Supports {packet}, {prompt}, {schema}, {output}."
    ),
)
@click.option("--model", default=None, help="Optional model name for Codex or Claude runners.")
@click.option("--timeout-seconds", type=int, default=300, show_default=True)
@click.option("--event-limit", type=int, default=120, show_default=True)
@click.option("--limit", type=int, default=None)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=Path(".cache/trace-corpus"),
    show_default=True,
)
@click.option(
    "--packet-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional directory to persist review packets.",
)
@click.option(
    "--adjudication-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional directory to persist agent adjudication JSON.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
    show_default=True,
)
def corpus_adjudicate_command(
    manifest: Path,
    runner: str,
    command_template: str | None,
    model: str | None,
    timeout_seconds: int,
    event_limit: int,
    limit: int | None,
    cache_dir: Path,
    packet_dir: Path | None,
    adjudication_dir: Path | None,
    output_format: str,
) -> None:
    """Run an external agent adjudicator over trace review packets."""
    report = adjudicate_manifest(
        manifest,
        runner=runner,
        cache_dir=cache_dir,
        limit=limit,
        packet_dir=packet_dir,
        adjudication_dir=adjudication_dir,
        command_template=command_template,
        model=model,
        timeout_seconds=timeout_seconds,
        event_limit=event_limit,
    )
    payload = report.to_dict()
    click.echo(_render_corpus_adjudication(report, output_format, payload))


def _load_report_sessions(
    session_dirs: tuple[Path, ...],
    trace_files: tuple[Path, ...],
    limit: int | None,
) -> list[Any]:
    sessions = []
    for trace_file in trace_files:
        sessions.append(parse_trace_file(trace_file))

    if session_dirs:
        roots = list(session_dirs)
    elif trace_files:
        roots = []
    else:
        roots = [path for path in DEFAULT_SESSION_DIRS if path.exists()]
    remaining = None if limit is None else max(limit - len(sessions), 0)
    for root in roots:
        root_files = discover_trace_files(root)
        if remaining is not None:
            root_files = root_files[:remaining]
        for trace_file in root_files:
            sessions.append(parse_trace_file(trace_file))
        if remaining is not None:
            remaining = max(limit - len(sessions), 0)
            if remaining == 0:
                break

    if limit is not None:
        sessions = sessions[:limit]
    return sessions


def _render_single_session(
    session: Any,
    report: ClassificationReport | None,
    output_format: str,
    payload: dict[str, Any],
) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    if output_format == "markdown":
        lines = [
            f"# Trace Analysis: {session.trace_path.name}",
            "",
            f"- Source: `{session.source}`",
            f"- Session ID: `{session.session_id or 'unknown'}`",
            f"- Models: `{', '.join(session.model_ids) or 'unknown'}`",
            f"- Events: `{len(session.events)}`",
            f"- Tool calls: `{len(session.tool_calls())}`",
            f"- Tool results: `{len(session.tool_results())}`",
            f"- Reasoning events: `{len(session.reasoning_events())}`",
            f"- Errors: `{len(session.errors())}`",
        ]
        if report:
            lines.extend(["", "## Findings"])
            if report.findings:
                lines.extend(
                    f"- `{finding.failure_mode_id}`: {finding.rationale}"
                    for finding in report.findings
                )
            else:
                lines.append("- No classifier findings.")
        return "\n".join(lines)

    lines = [
        f"Trace: {session.trace_path}",
        f"Source: {session.source}",
        f"Session ID: {session.session_id or 'unknown'}",
        f"Models: {', '.join(session.model_ids) or 'unknown'}",
        f"Events: {len(session.events)}",
        f"Tool calls: {len(session.tool_calls())}",
        f"Tool results: {len(session.tool_results())}",
        f"Reasoning events: {len(session.reasoning_events())}",
        f"Errors: {len(session.errors())}",
    ]
    if report:
        lines.append("Findings:")
        if report.findings:
            lines.extend(
                f"- {finding.failure_mode_id}: {finding.rationale}" for finding in report.findings
            )
        else:
            lines.append("- None")
    return "\n".join(lines)


def _render_reports(
    reports: list[ClassificationReport],
    output_format: str,
    payload: dict[str, Any],
) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    if output_format == "markdown":
        lines = ["# Session Classification Report", ""]
        lines.extend(_aggregate_markdown_lines(reports))
        lines.append("")
        lines.append("## Sessions")
        for report in reports:
            lines.append(f"- `{report.session.trace_path.name}`: {len(report.findings)} findings")
        return "\n".join(lines)

    lines = ["Session classification summary:"]
    lines.extend(_aggregate_text_lines(reports))
    lines.append("Sessions:")
    for report in reports:
        lines.append(f"- {report.session.trace_path.name}: {len(report.findings)} findings")
    return "\n".join(lines)


def _render_aggregate_report(
    reports: list[ClassificationReport],
    output_format: str,
    payload: dict[str, Any],
) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    if output_format == "markdown":
        lines = ["# Aggregate Trace Report", ""]
        lines.extend(_aggregate_markdown_lines(reports))
        return "\n".join(lines)

    lines = ["Aggregate trace report:"]
    lines.extend(_aggregate_text_lines(reports))
    return "\n".join(lines)


def _render_corpus_manifest(
    manifest: Any,
    summary: dict[str, Any],
    output_format: str,
    payload: dict[str, Any],
) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    if output_format == "markdown":
        lines = [
            f"# Trace Corpus Manifest: {manifest.name}",
            "",
            f"- Artifacts: `{summary['artifact_count']}`",
            f"- Fetchable: `{summary['fetchable_artifact_count']}`",
            f"- Reviewed: `{summary['reviewed_artifact_count']}`",
            "",
            "## Locator Kinds",
        ]
        if summary["locator_counts"]:
            lines.extend(
                f"- `{kind}`: `{count}`" for kind, count in summary["locator_counts"].items()
            )
        else:
            lines.append("- None")
        lines.extend(["", "## Artifacts"])
        for artifact in manifest.artifacts:
            lines.append(
                f"- `{artifact.artifact_id}`: `{artifact.locator.kind}` "
                f"({artifact.review_status})"
            )
        return "\n".join(lines)

    lines = [
        f"Trace corpus manifest: {manifest.name}",
        f"Artifacts: {summary['artifact_count']}",
        f"Fetchable: {summary['fetchable_artifact_count']}",
        f"Reviewed: {summary['reviewed_artifact_count']}",
        "Locator kinds:",
    ]
    if summary["locator_counts"]:
        lines.extend(f"- {kind}: {count}" for kind, count in summary["locator_counts"].items())
    else:
        lines.append("- None")
    lines.append("Artifacts:")
    for artifact in manifest.artifacts:
        lines.append(
            f"- {artifact.artifact_id}: {artifact.locator.kind} ({artifact.review_status})"
        )
    return "\n".join(lines)


def _render_corpus_evaluation(
    evaluation: Any,
    output_format: str,
    payload: dict[str, Any],
    written_packets: list[Path],
) -> str:
    summary = evaluation.summary()
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    if output_format == "markdown":
        lines = [
            f"# Corpus Evaluation: {evaluation.manifest.name}",
            "",
            f"- Artifacts: `{summary['artifact_count']}`",
            f"- Evaluated: `{summary['evaluated_count']}`",
            f"- Reviewed: `{summary['reviewed_count']}`",
            "",
            "## Status Counts",
        ]
        if summary["status_counts"]:
            lines.extend(
                f"- `{status}`: `{count}`"
                for status, count in summary["status_counts"].items()
            )
        else:
            lines.append("- None")
        lines.extend(["", "## Failure Mode Counts"])
        if summary["failure_mode_counts"]:
            lines.extend(
                f"- `{mode_id}`: `{count}`"
                for mode_id, count in summary["failure_mode_counts"].items()
            )
        else:
            lines.append("- None")
        if summary["missing_expected_counts"]:
            lines.extend(["", "## Missing Expected Labels"])
            lines.extend(
                f"- `{mode_id}`: `{count}`"
                for mode_id, count in summary["missing_expected_counts"].items()
            )
        if summary["violated_absent_counts"]:
            lines.extend(["", "## Violated Absent Labels"])
            lines.extend(
                f"- `{mode_id}`: `{count}`"
                for mode_id, count in summary["violated_absent_counts"].items()
            )
        lines.extend(["", "## Artifacts"])
        for item in evaluation.artifacts:
            finding_ids = (
                ", ".join(finding.failure_mode_id for finding in item.report.findings)
                if item.report
                else "none"
            )
            lines.append(f"- `{item.artifact.artifact_id}` [{item.status}]: `{finding_ids}`")
        if written_packets:
            lines.extend(["", "## Review Packets"])
            lines.extend(f"- `{path}`" for path in written_packets)
        return "\n".join(lines)

    lines = [
        f"Corpus evaluation: {evaluation.manifest.name}",
        f"Artifacts: {summary['artifact_count']}",
        f"Evaluated: {summary['evaluated_count']}",
        f"Reviewed: {summary['reviewed_count']}",
        "Status counts:",
    ]
    if summary["status_counts"]:
        lines.extend(
            f"- {status}: {count}" for status, count in summary["status_counts"].items()
        )
    else:
        lines.append("- None")
    lines.append("Failure mode counts:")
    if summary["failure_mode_counts"]:
        lines.extend(
            f"- {mode_id}: {count}"
            for mode_id, count in summary["failure_mode_counts"].items()
        )
    else:
        lines.append("- None")
    if summary["missing_expected_counts"]:
        lines.append("Missing expected labels:")
        lines.extend(
            f"- {mode_id}: {count}"
            for mode_id, count in summary["missing_expected_counts"].items()
        )
    if summary["violated_absent_counts"]:
        lines.append("Violated absent labels:")
        lines.extend(
            f"- {mode_id}: {count}"
            for mode_id, count in summary["violated_absent_counts"].items()
        )
    lines.append("Artifacts:")
    for item in evaluation.artifacts:
        if item.report:
            finding_ids = ", ".join(finding.failure_mode_id for finding in item.report.findings)
            finding_text = finding_ids or "none"
        else:
            finding_text = item.error or "none"
        lines.append(f"- {item.artifact.artifact_id} [{item.status}]: {finding_text}")
    if written_packets:
        lines.append("Review packets:")
        lines.extend(f"- {path}" for path in written_packets)
    return "\n".join(lines)


def _render_corpus_adjudication(
    report: Any,
    output_format: str,
    payload: dict[str, Any],
) -> str:
    summary = report.summary()
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    if output_format == "markdown":
        lines = [
            f"# Corpus Adjudication: {report.evaluation.manifest.name}",
            "",
            f"- Runner: `{report.runner_name}`",
            f"- Artifacts: `{summary['artifact_count']}`",
            f"- Adjudicated: `{summary['adjudicated_count']}`",
            f"- Reviewed: `{summary['reviewed_count']}`",
            "",
            "## Status Counts",
        ]
        if summary["status_counts"]:
            lines.extend(
                f"- `{status}`: `{count}`"
                for status, count in summary["status_counts"].items()
            )
        else:
            lines.append("- None")
        lines.extend(["", "## Agent Failure Mode Counts"])
        if summary["agent_failure_mode_counts"]:
            lines.extend(
                f"- `{mode_id}`: `{count}`"
                for mode_id, count in summary["agent_failure_mode_counts"].items()
            )
        else:
            lines.append("- None")
        if summary["rule_only_counts"]:
            lines.extend(["", "## Rule Only Counts"])
            lines.extend(
                f"- `{mode_id}`: `{count}`"
                for mode_id, count in summary["rule_only_counts"].items()
            )
        if summary["agent_only_counts"]:
            lines.extend(["", "## Agent Only Counts"])
            lines.extend(
                f"- `{mode_id}`: `{count}`"
                for mode_id, count in summary["agent_only_counts"].items()
            )
        lines.extend(["", "## Artifacts"])
        for item in report.artifacts:
            finding_ids = ", ".join(finding.failure_mode_id for finding in item.findings) or "none"
            lines.append(
                f"- `{item.artifact_evaluation.artifact.artifact_id}` "
                f"[{item.status}]: `{finding_ids}`"
            )
        return "\n".join(lines)

    lines = [
        f"Corpus adjudication: {report.evaluation.manifest.name}",
        f"Runner: {report.runner_name}",
        f"Artifacts: {summary['artifact_count']}",
        f"Adjudicated: {summary['adjudicated_count']}",
        f"Reviewed: {summary['reviewed_count']}",
        "Status counts:",
    ]
    if summary["status_counts"]:
        lines.extend(
            f"- {status}: {count}" for status, count in summary["status_counts"].items()
        )
    else:
        lines.append("- None")
    lines.append("Agent failure mode counts:")
    if summary["agent_failure_mode_counts"]:
        lines.extend(
            f"- {mode_id}: {count}"
            for mode_id, count in summary["agent_failure_mode_counts"].items()
        )
    else:
        lines.append("- None")
    if summary["rule_only_counts"]:
        lines.append("Rule only counts:")
        lines.extend(
            f"- {mode_id}: {count}"
            for mode_id, count in summary["rule_only_counts"].items()
        )
    if summary["agent_only_counts"]:
        lines.append("Agent only counts:")
        lines.extend(
            f"- {mode_id}: {count}"
            for mode_id, count in summary["agent_only_counts"].items()
        )
    lines.append("Artifacts:")
    for item in report.artifacts:
        if item.findings:
            finding_text = ", ".join(finding.failure_mode_id for finding in item.findings)
        else:
            finding_text = item.error or "none"
        lines.append(
            f"- {item.artifact_evaluation.artifact.artifact_id} [{item.status}]: {finding_text}"
        )
    return "\n".join(lines)


def _aggregate_reports(reports: list[ClassificationReport]) -> dict[str, Any]:
    counts = Counter()
    traces_with_findings = 0
    for report in reports:
        if report.findings:
            traces_with_findings += 1
        for finding in report.findings:
            counts[finding.failure_mode_id] += 1
    return {
        "trace_count": len(reports),
        "traces_with_findings": traces_with_findings,
        "failure_mode_counts": dict(counts.most_common()),
    }


def _aggregate_text_lines(reports: list[ClassificationReport]) -> list[str]:
    summary = _aggregate_reports(reports)
    lines = [
        f"Traces analyzed: {summary['trace_count']}",
        f"Traces with findings: {summary['traces_with_findings']}",
        "Failure mode counts:",
    ]
    if summary["failure_mode_counts"]:
        lines.extend(
            f"- {mode_id}: {count}"
            for mode_id, count in summary["failure_mode_counts"].items()
        )
    else:
        lines.append("- None")
    return lines


def _aggregate_markdown_lines(reports: list[ClassificationReport]) -> list[str]:
    summary = _aggregate_reports(reports)
    lines = [
        f"- Traces analyzed: `{summary['trace_count']}`",
        f"- Traces with findings: `{summary['traces_with_findings']}`",
        "## Failure Mode Counts",
    ]
    if summary["failure_mode_counts"]:
        lines.extend(
            f"- `{mode_id}`: `{count}`"
            for mode_id, count in summary["failure_mode_counts"].items()
        )
    else:
        lines.append("- None")
    return lines


def main() -> None:
    """Run the CLI."""
    cli()


if __name__ == "__main__":
    main()
