"""
CLI entrypoint for the Tokenized Assets Pipeline.

Usage:
  tap run "Chainlink" "chain.link"
  tap run "Chainlink" "chain.link" --timeout 45 --output results/
  tap batch companies.csv
  tap batch-sample   # Run on 3 sample companies
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..orchestrator import run_pipeline, PipelineRunner

console = Console()
logger = logging.getLogger(__name__)


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("--log-level", default="INFO", help="Logging level")
def cli(log_level: str) -> None:
    """Tokenized Assets Pipeline — 30-second data gathering system."""
    _setup_logging(log_level)


@cli.command()
@click.argument("company_name")
@click.argument("domain")
@click.option("--timeout", default=30, help="Pipeline timeout in seconds")
@click.option("--output", default="output", help="Output directory")
@click.option("--searxng-url", default=None, help="SearXNG URL override")
def run(company_name: str, domain: str, timeout: int, output: str, searxng_url: str | None) -> None:
    """Run the pipeline for a single company."""

    searxng = searxng_url or os.getenv("SEARXNG_URL", "http://localhost:8888")

    console.print(Panel(
        f"[bold cyan]Company:[/bold cyan] {company_name}\n"
        f"[bold cyan]Domain:[/bold cyan]   {domain}\n"
        f"[bold cyan]Timeout:[/bold cyan]  {timeout}s\n"
        f"[bold cyan]SearXNG:[/bold cyan]  {searxng}",
        title="🚀 Pipeline Run",
        expand=False,
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Gathering data...", total=None)

        result = asyncio.run(run_pipeline(
            company_name=company_name,
            domain=domain,
            searxng_url=searxng,
            timeout=timeout,
            output_dir=output,
        ))

        progress.update(task, description="Done!")

    # Display results
    _display_result(result, company_name)


@cli.command()
@click.argument("csv_file", type=click.Path(exists=True))
@click.option("--timeout", default=30, help="Pipeline timeout per company")
@click.option("--output", default="output", help="Output directory")
@click.option("--searxng-url", default=None, help="SearXNG URL override")
def batch(csv_file: str, timeout: int, output: str, searxng_url: str | None) -> None:
    """Run the pipeline for multiple companies from a CSV file.

    CSV must have columns: company_name, domain
    """
    searxng = searxng_url or os.getenv("SEARXNG_URL", "http://localhost:8888")
    companies = []

    with open(csv_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            companies.append((row["company_name"], row.get("domain", "")))

    console.print(f"[bold]Processing {len(companies)} companies...[/bold]\n")

    async def _run_all():
        results = []
        for name, domain in companies:
            console.print(f"  → {name} ({domain})")
            result = await run_pipeline(
                company_name=name,
                domain=domain or f"{name.lower().replace(' ', '')}.com",
                searxng_url=searxng,
                timeout=timeout,
                output_dir=output,
            )
            results.append((name, result))
        return results

    results = asyncio.run(_run_all())

    # Summary table
    table = Table(title="Batch Results")
    table.add_column("Company", style="cyan")
    table.add_column("Time (s)", style="green")
    table.add_column("Fill Rate", style="yellow")
    table.add_column("Errors", style="red")

    for name, result in results:
        total_time = result.timing.get("total", 0)
        fill_pct = f"{result.fill_rate * 100:.1f}%"
        errors = str(len(result.errors))
        table.add_row(name, str(total_time), fill_pct, errors)

    console.print(table)


@cli.command()
@click.option("--timeout", default=30, help="Pipeline timeout in seconds")
@click.option("--output", default="output", help="Output directory")
@click.option("--searxng-url", default=None, help="SearXNG URL override")
def batch_sample(timeout: int, output: str, searxng_url: str | None) -> None:
    """Run pipeline on 3 sample tokenized-asset companies."""

    samples = [
        ("Chainlink", "chain.link"),
        ("Circle", "circle.com"),
        ("Polymath", "polymath.network"),
    ]

    searxng = searxng_url or os.getenv("SEARXNG_URL", "http://localhost:8888")

    console.print("[bold]Running pipeline on 3 sample companies...[/bold]\n")

    async def _run_samples():
        results = []
        for name, domain in samples:
            console.print(f"  → {name} ({domain})")
            result = await run_pipeline(
                company_name=name,
                domain=domain,
                searxng_url=searxng,
                timeout=timeout,
                output_dir=output,
            )
            results.append((name, result))
        return results

    results = asyncio.run(_run_samples())

    # Summary
    table = Table(title="Sample Results")
    table.add_column("Company", style="cyan")
    table.add_column("Time (s)", style="green")
    table.add_column("Fill Rate", style="yellow")
    table.add_column("Phase 1", style="blue")
    table.add_column("Phase 2", style="blue")
    table.add_column("Phase 3", style="blue")
    table.add_column("Errors", style="red")

    for name, result in results:
        p1 = result.timing.get("phase1_gather", 0)
        p2 = result.timing.get("phase2_llm", 0)
        p3 = result.timing.get("phase3_validate", 0)
        total = result.timing.get("total", 0)
        fill_pct = f"{result.fill_rate * 100:.1f}%"
        table.add_row(name, str(total), fill_pct, f"{p1}s", f"{p2}s", f"{p3}s", str(len(result.errors)))

    console.print(table)


def _display_result(result: PipelineResult, company_name: str) -> None:
    """Display pipeline result in a rich format."""
    # Timing panel
    timing_lines = []
    for phase, secs in result.timing.items():
        timing_lines.append(f"  {phase}: [green]{secs}s[/green]")
    if result.errors:
        timing_lines.append("\n[red]Errors:[/red]")
        for err in result.errors[:5]:
            timing_lines.append(f"  • {err[:100]}")

    console.print(Panel(
        "\n".join(timing_lines),
        title=f"⏱ {company_name} — Timing",
        expand=False,
    ))

    # Fill rate
    fill_pct = result.fill_rate * 100
    color = "green" if fill_pct > 60 else "yellow" if fill_pct > 30 else "red"
    console.print(f"\nFill Rate: [{color}]{fill_pct:.1f}%[/{color}]")

    # Company profile
    profile = result.company_data.profile
    data_lines = []
    for field_name in profile.model_fields:
        val = getattr(profile, field_name)
        if val.value is not None:
            conf = f"({val.confidence:.0%})"
            data_lines.append(f"  {field_name}: {val.value} [dim]{conf}[/dim]")

    if data_lines:
        console.print(Panel(
            "\n".join(data_lines[:20]),
            title="📋 Company Profile",
            expand=False,
        ))


if __name__ == "__main__":
    cli()
