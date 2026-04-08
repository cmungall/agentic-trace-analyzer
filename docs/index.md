# Agentic Trace Analyzer

Ontology-backed analysis and classification for agentic AI session traces.

## Purpose

This repo does two related things:

- parse real agent traces from tools like Codex and Claude Code
- classify those traces against a structured failure-mode taxonomy

The taxonomy is modeled directly as a LinkML class tree, so the docs can expose
the actual schema hierarchy, enums, and leaf-class fields instead of just prose
about them.

## Documentation Map

<div class="grid cards" markdown>

-   __Failure Mode Taxonomy__

    ---

    Read the high-level taxonomy and category structure.

    [Open taxonomy](failure-mode-taxonomy.md)

-   __LinkML Schema__

    ---

    Browse generated schema docs for classes, slots, enums, and ontology entries.

    [Open schema reference](reference/index.md)

-   __Failure Mode Catalog__

    ---

    See every concrete failure mode with triggers, signals, mitigations, and related modes.

    [Open catalog](reference/failure-modes.md)

-   __Research Appendix__

    ---

    The original long-form narrative synthesis remains available as supporting material.

    [Open appendix](research-synthesis.md)

</div>

## Quick Start

```bash
uv sync --group dev
uv run agentic-trace-analyzer report text
```

Analyze a single trace:

```bash
uv run agentic-trace-analyzer analyze path/to/trace.jsonl
```

Classify a directory of traces:

```bash
uv run agentic-trace-analyzer classify ~/.codex/sessions --format markdown
```

Run the docs locally:

```bash
uv run mkdocs serve --dev-addr 127.0.0.1:8000
```
