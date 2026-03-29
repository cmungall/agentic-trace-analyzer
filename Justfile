set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just ci

sync:
    uv sync --all-groups

lint:
    uv run ruff check .

format:
    uv run ruff format .

test:
    uv run pytest

ci:
    uv run ruff check .
    uv run pytest

