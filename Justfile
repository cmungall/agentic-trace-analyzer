set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just ci

sync:
    uv sync --all-groups

gen-doc:
    mkdir -p docs/elements docs/schema
    rm -f docs/elements/*.md docs/schema/*.yaml
    cp src/agentic_trace_analyzer/schema/failure_modes.linkml.yaml docs/schema/failure_modes.linkml.yaml
    uv run gen-doc --genmeta --sort-by rank -d docs/elements src/agentic_trace_analyzer/schema/failure_modes.linkml.yaml >/dev/null

lint:
    uv run ruff check .

format:
    uv run ruff format .

test:
    uv run pytest

docs: gen-doc
    uv run mkdocs build --strict

docs-serve: gen-doc
    uv run mkdocs serve --dev-addr 127.0.0.1:8000

docs-deploy: gen-doc
    uv run mkdocs gh-deploy

ci:
    uv run ruff check .
    uv run pytest
