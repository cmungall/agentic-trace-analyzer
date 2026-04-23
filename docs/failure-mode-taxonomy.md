# Failure Mode Taxonomy

This taxonomy is the operational core of the project: it defines the failure
mode categories and concrete failure modes that the analyzer can map real
traces onto.

## Primary Reference

The current taxonomy is aligned to:

- Shah et al. (2026), *Characterizing Faults in Agentic AI: A Taxonomy of Types, Symptoms, and Root Causes*
- arXiv: <https://arxiv.org/abs/2603.06847>
- DOI: `10.48550/arXiv.2603.06847`
- Local copy: [2603.06847 PDF](papers/2603.06847-shah-et-al-characterizing-faults-in-agentic-ai.pdf)

This repo aligns its top-level dimensions to that paper's five architectural
fault dimensions, while keeping concrete leaf modes tuned for
trace-observable runtime failures.

!!! info "Source of truth"

    The taxonomy is modeled directly in the LinkML class hierarchy:

    - abstract classes are top-level paper-aligned dimensions
    - concrete descendant classes are trace failure modes
    - schema, class, enum, and permissible-value metadata carry source and alignment notes
    - class metadata carries severity, triggers, signals, mitigations, and relations

    The source of truth is:

    - `src/agentic_trace_analyzer/schema/failure_modes.linkml.yaml`

    The MkDocs reference pages are generated from that schema file.

## Top-Level Categories

| Category | Focus |
| --- | --- |
| Agent Cognition & Orchestration | Goal formation, planning, control flow, delegation, repetition, and termination failures |
| Tooling, Integration & Actuation | Tool misuse, unsafe actuation, permissions, and deterministic system-boundary failures |
| Perception, Context & Memory | Hallucination, state drift, context loss, prompt injection, and memory corruption |
| Runtime & Environment Grounding | Dependency, platform, quota, and resource-limit failures visible in traces |
| System Reliability & Observability | Verification gaps, silent degradation, fallback behaviour, and poor diagnosability |

Security and adversarial failures are still represented in the ontology, but
they are now modeled as cross-cutting trace extensions on relevant classes
instead of a sixth top-level bucket.

## How The Taxonomy Is Structured

The LinkML schema now defines:

- an abstract root class for the taxonomy
- five abstract paper-aligned dimension classes
- one concrete class per trace failure mode
- leaf-class attributes where failure-mode-specific fields make sense
- reference enums for `Shah2026FaultDimension`, `Shah2026SymptomClass`, and `Shah2026RootCauseCategory`
- a local `SeverityLevel` enum for project-specific operational severity
- schema/class/enum/PV annotations that preserve source and alignment metadata

This means the taxonomy is no longer split across a generic schema plus a
separate instance file. The hierarchy itself is the model.

## What To Read Next

<div class="grid cards" markdown>

-   __LinkML Overview__

    ---

    See the schema structure, source files, and generated counts.

    [Open schema reference](reference/index.md)

-   __Enums__

    ---

    Browse the LinkML enums, including the Shah et al. (2026) reference vocabularies
    and the repo's local `SeverityLevel`.

    [Open enum reference](reference/enums.md)

-   __Failure Mode Catalog__

    ---

    See every concrete failure mode, grouped by category with triggers,
    detection signals, mitigations, and related modes.

    [Open failure mode catalog](reference/failure-modes.md)

-   __Research Synthesis__

    ---

    The original long-form narrative synthesis is still available as an
    appendix, but it is no longer the primary docs landing page.

    [Open appendix](research-synthesis.md)

</div>

## Why LinkML Here

For this repo, LinkML is the right fit because the taxonomy is not just prose.
It is a typed model that drives:

- ontology-backed classifier output
- stable failure mode identifiers
- machine-readable enums and ranges
- paper/source provenance carried in schema metadata
- generated reference docs that stay aligned with the YAML sources
