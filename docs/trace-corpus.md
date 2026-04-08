# Trace Corpus

The classifier needs two different things:

1. a real source catalog of traces worth sampling, and
2. a reviewed evaluation corpus that can tell us when the classifier is actually wrong.

This repo now has both.

## Manifests

- `corpus/public_sources.yaml`
  Research-backed source catalog. It mixes public sharing surfaces like Traces, raw GitHub-exported session logs, and larger benchmark trajectory datasets on Hugging Face.
- `corpus/bootstrap_eval.yaml`
  Small mixed evaluation manifest. It combines reviewed local fixtures with a couple of public GitHub Claude/Codex exports that are directly ingestible today.

## Supported Adapters

The current ingestion layer can materialize these locator kinds:

- `local_file`
- `github_blob`
- `http`

The source catalog also records non-ingestible-yet locator kinds:

- `share_page`
- `huggingface_dataset`

Those are still useful because they let us track real public sources before we build the next adapter wave.

## Why This Shape

The immediate goal is not to crawl the internet blindly. It is to make classification evaluation disciplined.

- Keep a source catalog for discovery and provenance.
- Keep a smaller reviewed corpus for regression tests and scorekeeping.
- Export compact review packets so an agent can propose labels later without replacing the baseline harness.

This makes the rule-based classifier cheap to keep as a baseline while leaving a clean slot for agent-assisted labeling or second-pass adjudication.

## CLI

Validate a manifest:

```bash
uv run agentic-trace-analyzer corpus validate corpus/public_sources.yaml
```

Run the classifier against the bootstrap corpus:

```bash
uv run agentic-trace-analyzer corpus eval corpus/bootstrap_eval.yaml
```

Export compact JSON packets for agent-assisted review:

```bash
uv run agentic-trace-analyzer corpus eval \
  corpus/bootstrap_eval.yaml \
  --emit-review-packets build/review-packets
```

Each review packet includes:

- the artifact metadata
- the current rule-based findings
- a compact event digest with event IDs
- the allowed failure mode IDs from the LinkML taxonomy
- a strict JSON response contract for an external reviewer or agent

Run an actual agent adjudicator over the bootstrap corpus:

```bash
uv run agentic-trace-analyzer corpus adjudicate \
  corpus/bootstrap_eval.yaml \
  --runner codex \
  --packet-dir build/review-packets \
  --adjudication-dir build/adjudications
```

The adjudicator supports three runner modes:

- `codex`
  Uses `codex exec` with a JSON schema file and reads the final structured answer.
- `claude`
  Uses `claude -p` with `--json-schema` and tools disabled.
- `command`
  Runs any custom command template and supports `{packet}`, `{prompt}`, `{schema}`, and `{output}` placeholders.

This keeps the repo agnostic about which agent makes the judgment while still enforcing a strict structured output contract.

## Recommended Next Step

Use `bootstrap_eval.yaml` as the seed set, review the public GitHub samples manually, then promote the reviewed ones into a larger gold corpus before adding any model-based classifier.
