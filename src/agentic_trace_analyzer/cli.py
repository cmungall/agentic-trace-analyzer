"""Click entrypoint for the agentic trace analyzer."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import click

from agentic_trace_analyzer.classifier import ClassificationReport, classify_session
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
