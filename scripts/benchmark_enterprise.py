# mypy: ignore-errors
import asyncio
import sys
import time
from pathlib import Path

from rich.console import Console

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jaguar.analyzers import get_all_analyzers
from jaguar.core.engine import ScanEngine

console = Console()

DOMAINS = [
    "https://github.com",
    "https://gitlab.com",
    "https://google.com",
    "https://microsoft.com",
    "https://cloudflare.com",
    "https://openai.com",
    "https://stackoverflow.com",
    "https://wikipedia.org",
    "https://amazon.com",
]

async def run_benchmarks() -> None:
    console.print("[bold cyan]Running Enterprise Calibration Benchmarks[/bold cyan]")

    report = [
        "# JAGUAR Enterprise Calibration Benchmark",
        "",
        "This report validates JAGUAR's scoring engine against enterprise infrastructure.",
        "",
        "| Domain | Grade | Score | Confidence | HSTS Bypassed | CSP Bypassed | Runtime (s) | Redirects |",
        "|--------|-------|-------|------------|---------------|--------------|-------------|-----------|"
    ]

    engine = ScanEngine(enterprise_mode=True)
    get_all_analyzers()

    for domain in DOMAINS:
        console.print(f"Scanning {domain}...")
        start_time = time.time()

        try:
            res = await engine.scan(domain)
            runtime = time.time() - start_time

            grade = res.overall_score.grade.value if res.overall_score else "N/A"
            score = res.overall_score.score if res.overall_score else 0
            conf = res.confidence

            # Check bypass flags by looking at the findings source
            redirects = len(res.redirect_chain)

            hsts_bypassed = "No"
            csp_bypassed = "No"

            # Or we can look at the findings source
            sec_res = res.analyzer_results.get("security")
            if sec_res:
                for f in sec_res.findings:
                    if f.name == "hsts-implemented" and "Alternate" in f.source:
                        hsts_bypassed = "Yes"
                    if f.name == "csp-implemented" and "Alternate" in f.source:
                        csp_bypassed = "Yes"

            report.append(f"| {domain} | {grade} | {score} | {conf}% | {hsts_bypassed} | {csp_bypassed} | {runtime:.1f}s | {redirects} |")

        except Exception as e:
            console.print(f"[red]Error scanning {domain}: {e}[/red]")
            report.append(f"| {domain} | ERROR | ERROR | ERROR | ERROR | ERROR | ERROR | ERROR |")

    with open("BENCHMARK_REPORT.md", "w", encoding="utf-8") as file_out:
        file_out.write("\n".join(report) + "\n")

    console.print("[green]BENCHMARK_REPORT.md generated successfully.[/green]")

if __name__ == "__main__":
    if sys.platform == "win32":
        from asyncio.proactor_events import _ProactorBasePipeTransport  # type: ignore
        from functools import wraps
        def silence_event_loop_closed(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                try:
                    return func(self, *args, **kwargs)
                except (RuntimeError, ValueError):
                    pass
            return wrapper
        _ProactorBasePipeTransport.__del__ = silence_event_loop_closed(_ProactorBasePipeTransport.__del__)
    asyncio.run(run_benchmarks())
