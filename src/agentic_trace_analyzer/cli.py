"""Click entrypoint for the agentic trace analyzer."""

from __future__ import annotations

import click


@click.group(help="Analyze and classify agentic session traces.")
def cli() -> None:
    """Top-level CLI group."""


def main() -> None:
    """Run the CLI."""
    cli()


if __name__ == "__main__":
    main()
