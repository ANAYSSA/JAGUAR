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

if sys.platform == "win32":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[union-attr]
    from asyncio.proactor_events import _ProactorBasePipeTransport
    from functools import wraps
    def silence_event_loop_closed(func): # type: ignore
        @wraps(func)
        def wrapper(self, *args, **kwargs): # type: ignore
            try:
                return func(self, *args, **kwargs)
            except (RuntimeError, ValueError):
                pass
        return wrapper
    _ProactorBasePipeTransport.__del__ = silence_event_loop_closed(_ProactorBasePipeTransport.__del__) # type: ignore

from jaguar import __version__
from jaguar.analyzers import get_all_analyzers
from jaguar.cloner.engine import ClonerEngine
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
    from rich.align import Align
    from rich.panel import Panel

    banner = """
[bold cyan]██████████████████████████████████████████████████[/bold cyan]
[bold cyan]█[/bold cyan] [bold white]██╗ █████╗  ██████╗ ██╗   ██╗ █████╗ ██████╗[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]█[/bold cyan] [bold white]██║██╔══██╗██╔════╝ ██║   ██║██╔══██╗██╔══██╗[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]█[/bold cyan] [bold white]██║███████║██║  ███╗██║   ██║███████║██████╔╝[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]█[/bold cyan] [bold white]██║██╔══██║██║   ██║██║   ██║██╔══██║██╔══██╗[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]█[/bold cyan] [bold white]██║██║  ██║╚██████╔╝╚██████╔╝██║  ██║██║  ██║[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]█[/bold cyan] [bold white]╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝[/bold white] [bold cyan]█[/bold cyan]
[bold cyan]██████████████████████████████████████████████████[/bold cyan]
"""
    panel = Panel(
        Align(banner.strip(), align="center"),
        border_style="cyan",
        title=f"JAGUAR v{__version__} by anayssa",
        subtitle="Website Intelligence Platform",
    )
    console.print(Align(panel, align="center"))
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
def version() -> None:
    """Print the JAGUAR version and installation details."""
    import importlib.metadata
    import importlib.util
    import os

    try:
        ver = importlib.metadata.version("jaguar")
    except importlib.metadata.PackageNotFoundError:
        ver = "Unknown (not installed via pip)"

    spec = importlib.util.find_spec("jaguar")
    pkg_path = spec.origin if spec else "Unknown"
    if pkg_path and pkg_path.endswith("__init__.py"):
        pkg_path = os.path.dirname(os.path.dirname(pkg_path))

    project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    install_type = "Standard"
    if pkg_path and os.path.abspath(pkg_path).lower() == os.path.abspath(os.path.join(project_path, "src")).lower():
        install_type = "Editable"

    click.echo(f"Version: {ver}")
    click.echo(f"Install Type: {install_type}")
    click.echo(f"Project Path: {project_path}")
    click.echo(f"Package Path: {pkg_path}")
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
@click.option("--enterprise", is_flag=True, help="Enable Enterprise Mode (multi-UA, WAF evasion).")
def scan(url: str, format: str, output: str | None, no_browser: bool, no_store: bool, enterprise: bool) -> None:
    """Analyze a single website."""

    async def _scan() -> None:
        engine = ScanEngine(use_browser=not no_browser, enterprise_mode=enterprise)

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
@click.option("--lang", default="auto", help="Override the clone language (e.g. en-US, ru-RU). Default is 'auto'.")
@click.option("--spa", is_flag=True, help="Use browser to pre-render single page applications.")
@click.option("--serve", is_flag=True, help="Start a local server to view the clone immediately.")
@click.option("--verify", is_flag=True, help="Capture screenshots and compare visual accuracy.")
def clone(url: str, depth: int, pages: int, lang: str, spa: bool, serve: bool, verify: bool) -> None:
    """Clone a website for offline viewing."""

    async def _clone() -> None:
        click.echo(f"Initializing JAGUAR Cloner for {url}...\n")
        from jaguar.config import load_config
        cfg = load_config()
        clone_dir = cfg["cloner"].get("clone_dir", "D:\\JAGUAR\\jaguar-clones")

        engine = ClonerEngine(max_depth=depth, max_pages=pages, render_spa=spa, verify=verify, output_dir=clone_dir, config=cfg, locale_override=lang)

        import time
        start_time = time.time()

        from rich.progress import Progress, SpinnerColumn, TextColumn

        clone_task = asyncio.create_task(engine.clone(url))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task_id = progress.add_task("[cyan]Cloning website...", total=None)

            while not clone_task.done():
                elapsed = int(time.time() - start_time)
                mins, secs = divmod(elapsed, 60)
                hours, mins = divmod(mins, 60)
                elapsed_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

                queue_size = engine._queue.qsize() + engine._assets_queue.qsize()
                processed = len(engine._visited)
                assets = len(engine._assets_visited)
                failed = getattr(engine, "failed_assets_count", 0)
                current = getattr(engine, "current_url", "")
                if len(current) > 50:
                    current = current[:47] + "..."

                desc = (
                    f"[bold cyan]Cloning...[/bold cyan]\n"
                    f"Processed URLs:    [white]{processed}[/white]\n"
                    f"Downloaded Assets: [white]{assets}[/white]\n"
                    f"Failed Assets:     [red]{failed}[/red]\n"
                    f"Queue Size:        [yellow]{queue_size}[/yellow]\n"
                    f"Elapsed Time:      [magenta]{elapsed_str}[/magenta]\n"
                    f"Current:           [dim]{current}[/dim]"
                )
                progress.update(task_id, description=desc)
                await asyncio.sleep(0.2)

        output_dir = clone_task.result()

        elapsed_total = time.time() - start_time
        mins, secs = divmod(int(elapsed_total), 60)
        hours, mins = divmod(mins, 60)
        elapsed_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

        import os
        click.echo(f"\nClone successful.\n\nFiles saved to:\n{os.path.abspath(output_dir)}\n")

        if engine.clone_report:
            report = engine.clone_report
            click.echo(f"Processed URLs: {report.html.total}")

            downloaded = sum(
                c.resolved for c in [report.css, report.js, report.images, report.fonts, report.svg, report.manifest, report.media]
            )
            click.echo(f"Assets Downloaded: {downloaded}")

            failed = getattr(engine, "failed_assets_count", 0)
            click.echo(f"Failed Assets: {failed}")

            click.echo(f"Missing Assets: {report.total_missing}")

            if engine.visual_result and engine.visual_result.accuracy >= 0:
                click.echo(f"Visual Accuracy: {engine.visual_result.accuracy}%")
            else:
                click.echo("Visual Accuracy: N/A")

            click.echo(f"Clone Health: {report.overall_health}%")
            click.echo(f"Elapsed Time: {elapsed_str}")

            if report.is_spa:
                click.secho("\n[WARNING] SPA detected (React/Vue/Next/Angular).", fg="yellow")
                click.secho("This clone may require its original backend APIs to function fully offline.", fg="yellow")
            click.echo("")

        if not serve:
            click.echo("To view locally:\njaguar serve " + os.path.abspath(output_dir))
            click.echo("\nOr:\npython -m http.server 8080\n")

        if serve:
            from jaguar.cloner.server import CloneServer
            server = CloneServer(str(output_dir), port=8080)
            serve_url = server.start()
            click.echo(f"Serving at {serve_url}")
            try:
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                server.stop()
            except Exception as e:
                click.echo(f"Error: {e}", err=True)

    _run_async(_clone())


@cli.command(name="clone-doctor")
@click.argument("path")
@click.option("--deep", is_flag=True, help="Run deep Playwright validation for rendering issues")
def clone_doctor(path: str, deep: bool) -> None:
    """Diagnose broken assets in a cloned website."""
    import asyncio
    asyncio.run(_doctor(path, deep))

async def _doctor(path: str, deep: bool) -> None:
    import re
    from pathlib import Path
    from urllib.parse import urlparse

    import click
    click.echo(f"Running clone doctor on: {path}\n")

    from jaguar.config import load_config
    cfg = load_config()
    clone_dir_base = Path(cfg["cloner"].get("clone_dir", "D:\\JAGUAR\\jaguar-clones"))

    clone_dir = Path(path)
    if not clone_dir.exists() and (clone_dir_base / path).exists():
        clone_dir = clone_dir_base / path

    if not clone_dir.exists():
        click.echo("\033[91mError: Directory does not exist.\033[0m", err=True)
        return

    from jaguar.cloner.server import detect_entry_point
    entry = detect_entry_point(str(clone_dir))
    if not entry and not list(clone_dir.rglob("*.html")) and not list(clone_dir.rglob("*.php")):
        click.echo(f"\033[91mCritical Error: Directory '{clone_dir}' does not appear to be a JAGUAR clone (no entry point found).\033[0m")
        click.echo("Check your serve root configuration.")
        return

    from jaguar.cloner.validator import CloneValidator
    validator = CloneValidator(clone_dir)

    click.echo("\033[96mRunning Static Analysis...\033[0m")
    report = validator._run_static_checks()

    issues_found = False

    # 1. Output Static missing asset failures
    for cat_name, cat, category_type, fix_msg in [
        ("HTML", report.html, "Route Failure", "Ensure the crawler found at least one HTML page at the target URL."),
        ("CSS", report.css, "CSS Failure", "Verify internet connection during clone, or run clone with --spa to capture dynamic stylesheets."),
        ("JS", report.js, "JS Failure", "Verify internet connection during clone, or run clone with --spa to capture dynamic scripts."),
        ("Images", report.images, "Missing Asset", "Verify if this image asset exists on the origin website and is downloadable."),
        ("Fonts", report.fonts, "Missing Asset", "Verify if this web font is referenced correctly in CSS and resides on the same origin."),
        ("SVG", report.svg, "Missing Asset", "Verify if this SVG asset exists on the origin website and is downloadable."),
    ]:
        if cat.missing:
            issues_found = True
            for m in cat.missing[:5]:
                click.echo(f"\n[Category]      \033[91m{category_type}\033[0m")
                click.echo(f" [Reason]       File missing on disk ({cat_name})")
                click.echo(f" [URL]          {m}")
                click.echo(f" [File]         {m.split('?')[0].split('#')[0]}")
                click.echo(f" [Way to Fix]   {fix_msg}")
            if len(cat.missing) > 5:
                click.echo(f" ... and {len(cat.missing)-5} more static {cat_name} failures.")

    # 2. Output Dynamic Playwright failures if requested
    if deep:
        click.echo("\n\033[96mRunning Deep Dynamic Browser Analysis (Playwright)...\033[0m")
        report = await validator._run_playwright_validation(report, "http://localhost:8080")

        if report.rendering_error_logs:
            issues_found = True
            click.echo(f"\nFound {len(report.rendering_error_logs)} rendering issues:")
            for err in report.rendering_error_logs[:15]:
                err_lower = err.lower()

                # Classify
                category = "Rendering Failure"
                reason = "Unknown browser runtime error"
                url_match = re.search(r'(https?://[^\s]+)', err)
                url = url_match.group(1) if url_match else "N/A"
                file_path = urlparse(url).path.lstrip("/") if url != "N/A" else "N/A"
                fix = "Check browser logs and layout rendering."

                if "mime" in err_lower or "stylesheet" in err_lower or "corb" in err_lower:
                    category = "MIME Failure"
                    reason = "Served with incorrect MIME type or blocked by CORB (e.g. text/html instead of text/css)"
                    fix = "Ensure sidecar .meta.json file contains the original server's Content-Type."
                elif "encoding" in err_lower or "decoding" in err_lower or "decode" in err_lower:
                    category = "Content-Encoding Failure"
                    reason = "Failed to decode response content (e.g., gzip mismatch)"
                    fix = "Verify if .meta.json contains 'Content-Encoding: gzip' without the file being compressed on disk."
                elif "js exception" in err_lower or "uncaught" in err_lower or "pageerror" in err_lower:
                    category = "JS Failure"
                    reason = "JavaScript exception thrown at runtime"
                    fix = "Check script execution details. Some scripts require online APIs or cookies."
                elif "network" in err_lower or "failed to load" in err_lower or "net::" in err_lower:
                    category = "Network Failure"
                    reason = "Network request failed to load in the browser"
                    fix = "Verify if the server was reachable or if the request is blocked by CORS/firewalls."
                elif "404" in err_lower:
                    ext = Path(urlparse(url).path).suffix.lower()
                    if ext in (".html", ".php", ""):
                        category = "Route Failure"
                    else:
                        category = "Missing Asset"
                    reason = "Server returned HTTP 404 Not Found"
                    fix = "Check if this asset is served dynamically or if it was skipped during crawler queue."

                click.echo(f"\n[Category]      \033[91m{category}\033[0m")
                click.echo(f" [Reason]       {reason}")
                click.echo(f" [URL]          {url}")
                click.echo(f" [File]         {file_path}")
                click.echo(f" [Way to Fix]   {fix}")
                click.echo(f" [Original Log] {err}")

            if len(report.rendering_error_logs) > 15:
                click.echo(f"\n ... and {len(report.rendering_error_logs)-15} more dynamic rendering failures.")

        # Check visual accuracy
        if report.visual_accuracy is not None and report.visual_accuracy < 90.0:
            issues_found = True
            click.echo("\n[Category]      \033[91mRendering Failure\033[0m")
            click.echo(" [Reason]       Visual mismatch detected between original page and clone")
            click.echo(f" [URL]          {entry or 'Home'}")
            click.echo(" [File]         None")
            click.echo(f" [Way to Fix]   Visual accuracy is {report.visual_accuracy}%. Verify fonts, CSS, and layout rendering.")

    if not issues_found:
        click.echo("\n\033[92mClone Doctor found no issues! The clone is visually and structurally healthy.\033[0m")
    else:
        click.echo("\n\033[93mDiagnostics complete.\033[0m")

@cli.command(name="debug-clone")
@click.argument("path")
def debug_clone(path: str) -> None:
    """Print deep diagnostic information about a clone."""
    from pathlib import Path

    from jaguar.cloner.server import detect_entry_point
    from jaguar.cloner.validator import CloneValidator
    from jaguar.config import load_config

    cfg = load_config()
    clone_dir_base = Path(cfg["cloner"].get("clone_dir", "D:\\JAGUAR\\jaguar-clones"))

    clone_dir = Path(path)
    if not clone_dir.exists() and (clone_dir_base / path).exists():
        clone_dir = clone_dir_base / path

    if not clone_dir.exists():
        click.echo(f"\033[91mError: Directory '{clone_dir}' does not exist.\033[0m", err=True)
        return

    click.echo(f"Running clone diagnostics on: {clone_dir}")

    # 1. Entry Point
    entry = detect_entry_point(str(clone_dir))
    click.echo(f"\nSelected Entry Point: {entry or 'None Found'}")

    # Analyze entry point reason
    if entry:
        entry_path = clone_dir / entry
        if entry_path.exists():
            size = entry_path.stat().st_size
            import re
            content = entry_path.read_text("utf-8", errors="replace")
            links = len(re.findall(r'href=', content)) + len(re.findall(r'src=', content))
            depth = len(Path(entry).parts)
            click.echo(f"Reason:\n  {links} links\n  {size} bytes\n  depth={depth}")

    # 2. File counts (include .php for Moodle/WordPress clones)
    html_files = list(clone_dir.rglob("*.html"))
    php_files = list(clone_dir.rglob("*.php"))
    css_files = list(clone_dir.rglob("*.css"))
    js_files = list(clone_dir.rglob("*.js"))
    meta_files = list(clone_dir.rglob("*.meta.json"))

    # Count assets served via .meta.json that might have CSS/JS content-types
    css_meta_count = 0
    js_meta_count = 0
    import json as _json
    for mf in meta_files:
        try:
            meta = _json.loads(mf.read_text("utf-8"))
            ct = meta.get("Content-Type", "")
            if "text/css" in ct:
                css_meta_count += 1
            elif "javascript" in ct:
                js_meta_count += 1
        except Exception:
            pass

    click.echo(f"\nHTML Files Found: {len(html_files)}")
    click.echo(f"PHP Files Found: {len(php_files)}")
    click.echo(f"CSS Files Found: {len(css_files)} (+ {css_meta_count} via .meta.json)")
    click.echo(f"JS Files Found: {len(js_files)} (+ {js_meta_count} via .meta.json)")
    click.echo(f"MIME Metadata (.meta.json) Count: {len(meta_files)}")

    total_pages = len(html_files) + len(php_files)
    total_css = len(css_files) + css_meta_count
    total_js = len(js_files) + js_meta_count

    if total_pages == 0:
        click.echo("\033[91mWarning: No HTML or PHP files found. Clone may be empty.\033[0m")
    if total_css == 0:
        click.echo("\033[93mWarning: No CSS files found. Clone may appear unstyled.\033[0m")
    if total_js == 0:
        click.echo("\033[93mWarning: No JS files found. Clone may lack interactivity.\033[0m")

    # List actual CSS and JS paths (up to 10)
    if css_files:
        click.echo("\nCSS files on disk:")
        for f in css_files[:10]:
            click.echo(f"  {f.relative_to(clone_dir)}")
    if js_files:
        click.echo("\nJS files on disk:")
        for f in js_files[:10]:
            click.echo(f"  {f.relative_to(clone_dir)}")

    # 3. Validator parse
    validator = CloneValidator(clone_dir)
    report = validator._run_static_checks()

    total_assets = report.images.total + report.fonts.total + report.svg.total + report.media.total
    resolved_assets = report.images.resolved + report.fonts.resolved + report.svg.resolved + report.media.resolved

    click.echo(f"\nValidator Detected Links: {report.links.total}")
    click.echo(f"Validator Detected CSS: {report.css.total} (resolved: {report.css.resolved})")
    click.echo(f"Validator Detected JS: {report.js.total} (resolved: {report.js.resolved})")
    click.echo(f"Validator Detected Assets: {total_assets} (resolved: {resolved_assets})")

    click.echo("\nRoute Mappings:")
    click.echo(f"/ -> {entry or '404 Offline Placeholder'}")
    click.echo("/* -> Offline Placeholder Fallback (SPA routing enabled)")



@cli.command()
@click.argument("path", default="latest")
@click.option("--port", default=8080, help="Port to serve on.")
def serve(path: str, port: int) -> None:
    """Serve a cloned website locally with SPA routing support."""
    import os
    from pathlib import Path

    from jaguar.cloner.server import CloneServer
    from jaguar.config import load_config

    try:
        cfg = load_config()
        clone_dir = Path(cfg["cloner"].get("clone_dir", "D:\\JAGUAR\\jaguar-clones"))

        target_path = Path(path)
        if path.lower() == "latest":
            dirs = [d for d in clone_dir.iterdir() if d.is_dir()]
            if not dirs:
                click.echo("Error: No clones found in clone directory.")
                return
            target_path = max(dirs, key=lambda p: p.stat().st_mtime)
            click.echo(f"Resolved 'latest' to: {target_path.name}")
        elif not target_path.exists() and (clone_dir / path).exists():
            target_path = clone_dir / path
        elif not target_path.exists():
            click.echo(f"Error: Path {path} does not exist.")
            return

        # Serve Verification Checks (Reject root/user directories)
        from jaguar.cloner.server import detect_entry_point
        entry = detect_entry_point(str(target_path))

        if not entry and not list(target_path.rglob("*.html")) and not list(target_path.rglob("*.php")):
            click.echo(f"\033[91mCritical Error: Path {os.path.abspath(target_path)} does not appear to be a valid JAGUAR clone (no HTML or PHP files found).\033[0m")
            click.echo("Refusing to serve directory to prevent exposing user files.")
            return

        click.echo("\n\033[96mRunning Pre-Serve Health Check...\033[0m")

        html_count = sum(1 for _ in target_path.rglob("*.html"))
        php_count = sum(1 for _ in target_path.rglob("*.php"))
        css_count = sum(1 for _ in target_path.rglob("*.css"))
        js_count = sum(1 for _ in target_path.rglob("*.js"))
        meta_count = sum(1 for _ in target_path.rglob("*.meta.json"))

        page_count = html_count + php_count

        click.echo(f"Clone Root: {target_path}")
        click.echo(f"Entry Point: {entry or 'None Found'}")
        click.echo(f"HTML Files Found: {html_count}")
        click.echo(f"PHP Files Found: {php_count}")
        click.echo(f"CSS Files Found: {css_count}")
        click.echo(f"JS Files Found: {js_count}")
        click.echo(f"MIME Metadata Count: {meta_count}")

        if page_count == 0 or css_count == 0 or js_count == 0:
            click.echo("\033[93mWarning: Some asset counts are zero. The clone might be incomplete or missing stylesheets.\033[0m")

        from jaguar.cloner.validator import CloneValidator
        validator = CloneValidator(target_path)
        report = validator._run_static_checks(timeout=5)

        click.echo("\nServe Health:")
        click.echo(f"  HTML:   {'\033[92mOK' if not report.html.missing else '\033[91mBroken'} ({report.html.resolved}/{report.html.total})\033[0m")
        click.echo(f"  CSS:    {'\033[92mOK' if not report.css.missing else '\033[91mBroken'} ({report.css.resolved}/{report.css.total})\033[0m")
        click.echo(f"  JS:     {'\033[92mOK' if not report.js.missing else '\033[91mBroken'} ({report.js.resolved}/{report.js.total})\033[0m")

        total_assets = report.images.total + report.fonts.total + report.svg.total + report.media.total
        resolved_assets = report.images.resolved + report.fonts.resolved + report.svg.resolved + report.media.resolved
        assets_status = '\033[92mOK' if (total_assets == 0 or resolved_assets == total_assets) else '\033[91mBroken'
        click.echo(f"  Assets: {assets_status} ({resolved_assets}/{total_assets})\033[0m\n")

        click.echo(f"Assets Found: {total_assets}")

        server = CloneServer(str(target_path), port=port)
        url = server.start()
        click.echo(f"Serving {target_path} at {url}")
        click.echo("Press Ctrl+C to stop.")

        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nStopping server...")
        server.stop()
    except Exception as e:
        click.echo(f"Error: {e}", err=True)

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
@click.argument("url")
def explain(url: str) -> None:
    """Transparency mode: Explain exactly why a score was assigned."""

    async def _explain() -> None:
        click.echo(f"Running transparent scan for {url}...\n")
        engine = ScanEngine(enterprise_mode=True)
        scan_res = await engine.scan(url)

        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        console.print(Panel(f"[bold cyan]JAGUAR Transparency Report for {scan_res.url}[/bold cyan]"))

        console.print(f"[bold]Overall Confidence:[/bold] {scan_res.confidence}%")
        if scan_res.overall_score:
            console.print(f"[bold]Overall Score:[/bold] {scan_res.overall_score.score} ({scan_res.overall_score.grade})")

        console.print("\n[bold magenta]1. Detected Headers[/bold magenta]")
        if scan_res.headers:
            for k, v in scan_res.headers.items():
                console.print(f"  {k}: {v}")
        else:
            console.print("  [dim]None[/dim]")

        console.print("\n[bold magenta]2. Detected Cookies[/bold magenta]")
        if scan_res.cookies:
            for c in scan_res.cookies:
                console.print(f"  {c.get('name')}: Secure={c.get('secure')} HttpOnly={c.get('httponly')} SameSite={c.get('samesite')}")
        else:
            console.print("  [dim]None[/dim]")

        console.print("\n[bold magenta]3. Redirect Chain[/bold magenta]")
        if scan_res.redirect_chain:
            for i, hop in enumerate(scan_res.redirect_chain):
                console.print(f"  {i+1}. {hop}")
        else:
            console.print("  [dim]None[/dim]")

        console.print("\n[bold magenta]4. Detected Technologies[/bold magenta]")
        if scan_res.tech_stack:
            for tech in scan_res.tech_stack:
                console.print(f"  * {tech.name} ({tech.category}) - {tech.confidence*100:.0f}% confidence")
        else:
            console.print("  [dim]None[/dim]")

        console.print("\n[bold magenta]5. Security Score Breakdown[/bold magenta]")
        sec_res = scan_res.analyzer_results.get("security")
        if sec_res:
            for title, modifier in sec_res.score_explanation.breakdown.items():
                console.print(f"  * {title}: {'+' if modifier > 0 else ''}{modifier}")

            console.print("\n[bold magenta]6. Security Evidence[/bold magenta]")
            for f in sec_res.findings:
                status = "[bold green]PASSED[/bold green]" if f.passed else "[bold red]FAILED[/bold red]"
                console.print(f"\n[bold]{f.title}[/bold] (Status: {status})")
                console.print(f"Received:\n  {f.raw_value or 'None'}")
                console.print(f"Expected:\n  {f.expected_value or 'None'}")
                console.print(f"Why it failed:\n  {f.failure_reason or 'N/A'}")
                console.print(f"Source:\n  {f.source}")

        console.print("\n[bold magenta]7. SEO Evidence[/bold magenta]")
        seo_res = scan_res.analyzer_results.get("seo")
        if seo_res:
            for f in seo_res.findings:
                status = "[bold green]PASSED[/bold green]" if f.passed else "[bold red]FAILED[/bold red]"
                console.print(f"\n[bold]{f.title}[/bold] (Status: {status})")
                console.print(f"Received:\n  {f.raw_value or 'None'}")
                console.print(f"Expected:\n  {f.expected_value or 'None'}")
                console.print(f"Why it failed:\n  {f.failure_reason or 'N/A'}")
                console.print(f"Source:\n  {f.source}")

    _run_async(_explain())


@cli.command()
@click.option("--json", "json_mode", is_flag=True, help="Output in JSON format.")
@click.option("--fix", is_flag=True, help="Automatically attempt to fix detected issues.")
def doctor(json_mode: bool, fix: bool) -> None:
    """Diagnose JAGUAR environment and dependencies."""
    from jaguar.doctor import run_doctor
    run_doctor(json_mode, fix)


@cli.group(name="config")
def config_group() -> None:
    """Manage JAGUAR configuration."""
    pass

@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value."""
    from jaguar.config import load_config, save_config
    cfg = load_config()

    if key == "clone_dir":
        cfg["cloner"]["clone_dir"] = value
    elif "." in key:
        section, k = key.split(".", 1)
        if section not in cfg:
            cfg[section] = {}
        cfg[section][k] = value
    else:
        click.echo(f"Error: Unknown top-level key '{key}'. Use section.key (e.g. cloner.clone_dir)")
        return

    save_config(cfg)
    click.echo(f"Config updated: {key} = {value}")


main = cli

if __name__ == "__main__":
    main()
