# Failure Mode Taxonomy

This taxonomy is the operational core of the project: it defines the failure
mode categories and concrete failure modes that the analyzer can map real
traces onto.

!!! info "Source of truth"

    The taxonomy is modeled directly in the LinkML class hierarchy:

    - abstract classes are top-level categories
    - concrete descendant classes are failure modes
    - class metadata carries severity, triggers, signals, mitigations, and relations

    The source of truth is:

    - `src/agentic_trace_analyzer/schema/failure_modes.linkml.yaml`

    The MkDocs reference pages are generated from that schema file.

## Top-Level Categories

| Category | Focus |
| --- | --- |
| Specification & Alignment | Misread goals, missing constraints, early commitment under ambiguity |
| Planning & Control | Multi-step execution, termination, repetition, and coordination failures |
| Tool & Actuation | Wrong tool use, unsafe tool execution, and boundary violations |
| Memory / Knowledge / State | Hallucination, context drift, and memory corruption |
| Monitoring & Recovery | Verification gaps, silent degradation, and resource issues |
| Security & Adversarial | Prompt injection, compromise, and poisoned external knowledge |

## How The Taxonomy Is Structured

The LinkML schema now defines:

- an abstract root class for the taxonomy
- six abstract category classes
- one concrete class per failure mode
- leaf-class attributes where failure-mode-specific fields make sense
- a `SeverityLevel` enum used inside class metadata

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

    Browse the LinkML enums, including `SeverityLevel`.

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
- generated reference docs that stay aligned with the YAML sources
