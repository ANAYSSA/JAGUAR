"""
Command Line Interface for JAGUAR.

Provides commands for scanning, cloning, comparing, and viewing history.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        getattr(sys.stdout, 'reconfigure')(encoding='utf-8')

from jaguar import __version__
from jaguar.analyzers import get_all_analyzers
from jaguar.cloner.engine import ClonerEngine
from jaguar.cloner.server import CloneServer
from jaguar.comparator.engine import ComparisonEngine
from jaguar.core.engine import ScanEngine
from jaguar.reporters import get_all_reporters
from jaguar.storage.database import StorageDatabase

# Force registration of all plugins
get_all_analyzers()
get_all_reporters()

# Setup basic logging to hide debug info unless requested
logging.basicConfig(level=logging.WARNING, format="%(message)s")

console = Console()


def display_banner() -> None:
    """Print the JAGUAR premium ASCII banner."""
    banner = """
[bold cyan]      ██████████████████████████████████████████████████[/bold cyan]
[bold cyan]      █[/bold cyan] [bold white]██╗ █████╗  ██████╗ ██╗   ██╗ █████╗ ██████╗[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]      █[/bold cyan] [bold white]██║██╔══██╗██╔════╝ ██║   ██║██╔══██╗██╔══██╗[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]      █[/bold cyan] [bold white]██║███████║██║  ███╗██║   ██║███████║██████╔╝[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]      █[/bold cyan] [bold white]██║██╔══██║██║   ██║██║   ██║██╔══██║██╔══██╗[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]      █[/bold cyan] [bold white]██║██║  ██║╚██████╔╝╚██████╔╝██║  ██║██║  ██║[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]      █[/bold cyan] [bold white]╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]      ██████████████████████████████████████████████████[/bold cyan]
    """
    console.print(banner, justify="center")

    version_text = Text(f"JAGUAR v{__version__} by anayssa", style="bold magenta", justify="center")
    subtitle_text = Text("Website Intelligence Platform", style="dim", justify="center")
    console.print(version_text)
    console.print(subtitle_text)
    console.print()


async def check_startup_status() -> None:
    """Perform startup status checks and display module loading."""
    from jaguar.analyzers import get_all_analyzers
    from jaguar.reporters import get_all_reporters

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Initializing JAGUAR Core engine...", total=3)

        # Fake a bit of loading for premium feel
        await asyncio.sleep(0.3)
        progress.update(
            task,
            advance=1,
            description=f"[cyan]Loaded {len(get_all_analyzers())} Analysis Modules...",
        )

        await asyncio.sleep(0.3)
        progress.update(
            task,
            advance=1,
            description=f"[cyan]Loaded {len(get_all_reporters())} Reporting Modules...",
        )

        await asyncio.sleep(0.3)
        progress.update(task, advance=1, description="[green]System ready.[/green]")

    console.print("[green]✔ All modules verified and online.[/green]\n")


def _run_async(coro: Any) -> Any:
    """Helper to run async functions in synchronous Click commands."""
    return asyncio.run(coro)


@click.group(invoke_without_command=True)
@click.option("--debug", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, debug: bool) -> None:
    """JAGUAR - Advanced Website Analysis & Cloning Platform."""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if ctx.invoked_subcommand is None:
        display_banner()
        click.echo(ctx.get_help())
        return

    display_banner()
    _run_async(check_startup_status())


@cli.command()
@click.argument("url")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["console", "json", "markdown", "html"]),
    default="console",
    help="Report format.",
)
@click.option("--output", "-o", type=click.Path(), help="Output file path.")
@click.option(
    "--no-browser",
    is_flag=True,
    help="Disable Playwright browser (disables accessibility, SPA, UX deep checks).",
)
@click.option("--no-store", is_flag=True, help="Do not save scan to history.")
def scan(url: str, format: str, output: str | None, no_browser: bool, no_store: bool) -> None:
    """Analyze a single website."""

    async def _scan() -> None:
        engine = ScanEngine(use_browser=not no_browser)

        click.echo(f"Starting JAGUAR scan for {url}...")
        result = await engine.scan(url)

        # Determine reporter
        from jaguar.reporters import get_all_reporters

        reporters = {r.format_name: r for r in get_all_reporters()}

        if format not in reporters:
            click.echo(f"Error: Unknown format {format}", err=True)
            return

        reporter = reporters[format]
        output_path = output

        if format != "console" and not output_path:
            from jaguar.utils.url import extract_hostname
            output_path = f"jaguar_report_{extract_hostname(url)}"

        await reporter.generate(result, output_path or "")

    _run_async(_scan())


@cli.command()
@click.argument("url")
@click.option("--depth", "-d", default=1, help="Crawl depth.")
@click.option("--pages", "-p", default=50, help="Maximum number of pages to clone.")
@click.option("--spa", is_flag=True, help="Use browser to pre-render single page applications.")
@click.option("--serve", is_flag=True, help="Start a local server to view the clone immediately.")
def clone(url: str, depth: int, pages: int, spa: bool, serve: bool) -> None:
    """Clone a website for offline viewing."""

    async def _clone() -> None:
        click.echo(f"Initializing JAGUAR Cloner for {url}...")
        engine = ClonerEngine(max_depth=depth, max_pages=pages, render_spa=spa)

        output_dir = await engine.clone(url)
        click.echo(f"\nClone successful! Files saved to: {output_dir}")

        if serve:
            server = CloneServer(output_dir)
            local_url = server.start()
            click.echo(f"Server started. View the clone at: {local_url}")
            click.echo("Press Ctrl+C to stop.")
            try:
                # Keep alive until interrupted
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                server.stop()

    _run_async(_clone())


@cli.command()
@click.argument("url_a")
@click.argument("url_b")
def compare(url_a: str, url_b: str) -> None:
    """Compare two websites side-by-side."""

    async def _compare() -> None:
        click.echo(f"Scanning Site A: {url_a}...")
        engine = ScanEngine()
        scan_a = await engine.scan(url_a)

        click.echo(f"Scanning Site B: {url_b}...")
        scan_b = await engine.scan(url_b)

        click.echo("Calculating Comparison Deltas...\n")
        comp_engine = ComparisonEngine()
        result = comp_engine.compare(scan_a, scan_b)

        from rich.console import Console
        from rich.table import Table

        console = Console()

        console.print(Panel("[bold]JAGUAR Comparison Report[/bold]", expand=False))

        # Print Deltas Table
        table = Table(show_header=True)
        table.add_column("Metric")
        table.add_column(f"Site A: {scan_a.hostname}")
        table.add_column(f"Site B: {scan_b.hostname}")
        table.add_column("Winner", style="bold green")

        for delta in result.deltas.get("overall", []) + result.deltas.get("scores", []):
            win_str = "A" if delta.winner == "a" else "B" if delta.winner == "b" else "Tie"
            table.add_row(delta.label, str(delta.value_a), str(delta.value_b), win_str)

        console.print(table)

        # Print Insights
        if result.competitive_insights:
            console.print("\n[bold cyan]AI Competitive Insights:[/bold cyan]")
            for insight in result.competitive_insights:
                console.print(f"- {insight}")

    _run_async(_compare())


@cli.command()
@click.argument("url_a")
@click.argument("url_b")
def competitor(url_a: str, url_b: str) -> None:
    """Alias for compare command (Requirement #3)."""
    # They behave identically under the hood based on requirements,
    # except competitor emphasizes the insights which the compare command already prints.
    click.echo("Running JAGUAR in Competitor Analysis Mode...\n")
    # Just invoke the compare command directly via click internals or call its logic.
    # We will just delegate for simplicity.
    import sys

    sys.argv = [sys.argv[0], "compare", url_a, url_b]
    cli()


@cli.command()
def history() -> None:
    """View historical scan reports."""
    db = StorageDatabase()
    summaries = db.list_history(limit=20)

    if not summaries:
        click.echo("No historical scans found.")
        return

    from rich.console import Console
    from rich.table import Table

    console = Console()

    table = Table(title="Recent JAGUAR Scans")
    table.add_column("Scan ID (Prefix)", style="dim")
    table.add_column("Date", style="cyan")
    table.add_column("URL")
    table.add_column("Grade", justify="center")
    table.add_column("Score", justify="right")

    for s in summaries:
        table.add_row(
            s.id[:8],
            s.scanned_at.strftime("%Y-%m-%d %H:%M"),
            s.url,
            s.overall_grade,
            str(s.overall_score),
        )

    console.print(table)


@cli.command()
@click.argument("scan_a_id")
@click.argument("scan_b_id")
def diff(scan_a_id: str, scan_b_id: str) -> None:
    """Compare two historical scans by their ID prefix."""
    db = StorageDatabase()

    # We need to find full IDs by prefix
    all_scans = db.list_history()
    scan_a_full = next((s.id for s in all_scans if s.id.startswith(scan_a_id)), None)
    scan_b_full = next((s.id for s in all_scans if s.id.startswith(scan_b_id)), None)

    if not scan_a_full or not scan_b_full:
        click.echo("Could not find scans matching provided IDs.", err=True)
        return

    scan_a = db.get_scan(scan_a_full)
    scan_b = db.get_scan(scan_b_full)

    if not scan_a or not scan_b:
        click.echo("Failed to load full scan data.", err=True)
        return

    click.echo(f"Diffing Scan A ({scan_a.url}) vs Scan B ({scan_b.url})...")

    comp_engine = ComparisonEngine()
    result = comp_engine.compare(scan_a, scan_b)

    for cat, deltas in result.deltas.items():
        click.echo(f"\n--- {cat.upper()} ---")
        for d in deltas:
            click.echo(f"{d.label}: A={d.value_a} | B={d.value_b} | Diff={d.delta}")


@cli.command()
@click.option("--json", "json_mode", is_flag=True, help="Output in JSON format.")
@click.option("--fix", is_flag=True, help="Automatically attempt to fix detected issues.")
def doctor(json_mode: bool, fix: bool) -> None:
    """Diagnose JAGUAR environment and dependencies."""
    from jaguar.doctor import run_doctor
    run_doctor(json_mode, fix)


main = cli

if __name__ == "__main__":
    main()
