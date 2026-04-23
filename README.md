# Agentic Trace Analyzer

Classify and analyze agentic AI session traces using ontology-backed failure mode taxonomies.

## Goals

1. **Parse agent traces** — read session logs from Claude Code (`.claude/projects/`), Codex (`.codex/sessions/`), OpenClaw, and generic JSONL formats
2. **Classify events** using a formal ontology of agentic failure modes (see `ontology/`)
3. **Detect patterns** — silent degradation, premature commitment, tool misuse, state desync, etc.
4. **Report** — structured analysis with evidence links back to trace events
5. **Integrate** with tmux-pilot (`tp`) for live session monitoring

## Failure Mode Ontology

The LinkML taxonomy is now aligned to Shah et al. (2026), *Characterizing Faults
in Agentic AI: A Taxonomy of Types, Symptoms, and Root Causes* (`10.48550/arXiv.2603.06847`).
The paper is stored locally at
`docs/papers/2603.06847-shah-et-al-characterizing-faults-in-agentic-ai.pdf`.

Five top-level dimensions follow the paper's architectural framing:

- **Agent Cognition & Orchestration** — goal/intent mismatch, choice overload, planning/control failures
- **Tooling, Integration & Actuation** — wrong tool selection, tool misuse, unsafe or unauthorized actions
- **Perception, Context & Memory** — hallucination, state desynchronization, prompt injection, memory poisoning
- **Runtime & Environment Grounding** — resource exhaustion and environment-coupled execution failures
- **System Reliability & Observability** — weak fallback, verification failure, and provenance gaps

Security and adversarial modes are still first-class in the ontology, but they are
modeled as cross-cutting trace extensions instead of a separate sixth top-level
bucket.

The ontology is modeled in LinkML (naturally) and serialized as OWL for reasoning.

## Architecture

- Python CLI + library
- LinkML schema for the failure mode ontology
- Trace parsers for Claude Code, Codex, OpenClaw session logs
- Event classifiers (rule-based baseline, agent-assisted review planned)
- Integration with tp (tmux-pilot) for live trace analysis

## Trace Corpus Workflow

The repo now has a concrete corpus/evaluation layer for testing classification work against
real traces instead of ad hoc examples.

- `corpus/public_sources.yaml` tracks researched public trace sources and benchmark datasets
- `corpus/bootstrap_eval.yaml` defines a small mixed evaluation set
- `agentic-trace-analyzer corpus validate ...` checks manifest structure and coverage
- `agentic-trace-analyzer corpus eval ...` resolves traces, runs the current classifier, and
  compares results against reviewed labels when present
- `--emit-review-packets` writes compact JSON packets for agent-assisted second-pass review
- `agentic-trace-analyzer corpus adjudicate ...` runs a structured agent adjudicator via
  `codex`, `claude`, or a custom command-template runner

## Documentation

The docs are built with MkDocs in the standard LinkML project pattern and can be
previewed locally with:

```bash
just gen-doc
uv run mkdocs serve --dev-addr 127.0.0.1:8000
```

The schema reference in `docs/elements/` is generated directly from
`src/agentic_trace_analyzer/schema/failure_modes.linkml.yaml` via LinkML
`gen-doc`, not maintained as hand-synced Markdown.

To publish manually to GitHub Pages:

```bash
just docs-deploy
```

The repo also includes `.github/workflows/deploy-docs.yaml`, modeled on the
current LinkML project template, so pushes to `main` publish the site to the
`gh-pages` branch. For the one-time repo setting, configure GitHub Pages to
deploy from the `gh-pages` branch root.
