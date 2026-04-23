# Agentic Trace Analyzer

Ontology-backed analysis and classification for agentic AI session traces.

The taxonomy is now aligned to Shah et al. (2026), *Characterizing Faults in
Agentic AI: A Taxonomy of Types, Symptoms, and Root Causes*, with a local copy
available at [2603.06847 PDF](papers/2603.06847-shah-et-al-characterizing-faults-in-agentic-ai.pdf).

## Purpose

This repo does two related things:

- parse real agent traces from tools like Codex and Claude Code
- classify those traces against a structured failure-mode taxonomy

The taxonomy is modeled directly as a LinkML class tree, so the docs can expose
the actual schema hierarchy, enums, and leaf-class fields instead of just prose
about them. The schema reference under `docs/elements/` is generated directly
from the LinkML source with `gen-doc`, not hand-synced Markdown. The top-level
dimensions follow the paper's five architectural fault dimensions; the leaf
modes remain trace-focused adaptations.

## Documentation Map

<div class="grid cards" markdown>

-   __Failure Mode Taxonomy__

    ---

    Read the high-level taxonomy and category structure.

    [Open taxonomy](failure-mode-taxonomy.md)

-   __LinkML Schema__

    ---

    Browse the generated LinkML schema documentation.

    [Open schema docs](elements/index.md)

-   __Failure Mode Catalog__

    ---

    Jump into the generated schema tree rooted at `FailureMode`.

    [Open root class](elements/FailureMode.md)

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
