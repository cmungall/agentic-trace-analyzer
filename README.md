# Agentic Trace Analyzer

Classify and analyze agentic AI session traces using ontology-backed failure mode taxonomies.

## Goals

1. **Parse agent traces** — read session logs from Claude Code (`.claude/projects/`), Codex (`.codex/sessions/`), OpenClaw, and generic JSONL formats
2. **Classify events** using a formal ontology of agentic failure modes (see `ontology/`)
3. **Detect patterns** — silent degradation, premature commitment, tool misuse, state desync, etc.
4. **Report** — structured analysis with evidence links back to trace events
5. **Integrate** with tmux-pilot (`tp`) for live session monitoring

## Failure Mode Ontology

Based on the taxonomy from deep research on agentic AI failure modes. Six top-level categories:

- **Specification & Alignment** — goal/intent mismatch, constraint omission, choice overload
- **Planning & Control** — insufficient planning, premature termination, step repetition, reasoning-action mismatch, multi-agent coordination breakdown
- **Tool & Actuation** — wrong tool selection, unauthorized actuation, unsafe output handling
- **Memory/Knowledge/State** — hallucination, state desynchronization, memory poisoning
- **Monitoring & Recovery** — weak fallback, verification failure, observability gaps, resource exhaustion
- **Security & Adversarial** — prompt injection, instruction hijack, knowledge-base poisoning

The ontology is modeled in LinkML (naturally) and serialized as OWL for reasoning.

## Architecture

- Python CLI + library
- LinkML schema for the failure mode ontology
- Trace parsers for Claude Code, Codex, OpenClaw session logs
- Event classifiers (rule-based + LLM-assisted)
- Integration with tp (tmux-pilot) for live trace analysis
