set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just ci

sync:
    uv sync --all-groups

gen-doc:
    uv run mkdocs build --strict

lint:
    uv run ruff check .

format:
    uv run ruff format .

test:
    uv run pytest

docs:
    uv run mkdocs build --strict

docs-serve:
    uv run mkdocs serve --dev-addr 127.0.0.1:8000

docs-deploy:
    uv run mkdocs gh-deploy

ci:
    uv run ruff check .
    uv run pytest
