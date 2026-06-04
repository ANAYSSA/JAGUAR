"""
Console reporter for JAGUAR.

Uses Rich to print beautiful, colored reports directly to the terminal.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from jaguar.reporters.base import BaseReporter

if TYPE_CHECKING:
    from jaguar.core.models import ScanResult

logger = logging.getLogger("jaguar.reporters.console")


class ConsoleReporter(BaseReporter):
    """Generates rich terminal reports."""

    name = "console"
    format_name = "console"

    async def generate(self, result: ScanResult, output_path: str, **options: Any) -> str:
        """
        Print the report to the console using Rich.
        Does not write to a file.
        """
        console = Console()

        # Header
        console.print()
        console.print(
            Panel(
                f"[bold cyan]JAGUAR Scan Report[/bold cyan]\n[white]{result.url}[/white]",
                expand=False,
                border_style="cyan",
            )
        )

        # Overall Score
        if result.overall_score:
            color = self._get_grade_color(result.overall_score.grade.value)
            console.print(
                f"\n[bold]Overall Grade:[/bold] [{color}]{result.overall_score.grade.value}[/{color}] ({result.overall_score.score}/100)"
            )
            console.print(f"[italic]{result.overall_score.summary}[/italic]\n")

        # Category Table
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Category", style="dim")
        table.add_column("Score", justify="right")
        table.add_column("Grade", justify="center")
        table.add_column("Summary")

        for name, ar in sorted(result.analyzer_results.items()):
            display_name = name.replace("_", " ").title()
            score = str(ar.score)
            grade = ar.grade.value
            color = self._get_grade_color(grade)
            summary = ar.score_explanation.summary

            table.add_row(display_name, score, f"[{color}]{grade}[/{color}]", summary)

        console.print(table)
        console.print()

        # Top Issues/Recommendations
        if result.recommendations:
            console.print("[bold red]Top Recommendations:[/bold red]")
            for i, rec in enumerate(result.recommendations[:5], 1):
                color = self._get_priority_color(rec.priority.value)
                console.print(f"[{color}]{i}. {rec.what}[/{color}]")
                console.print(f"   [dim]How:[/dim] {rec.how}")
            console.print()

        # Tech Stack
        if result.tech_stack:
            tech_tree = Tree("[bold blue]Detected Technology Stack[/bold blue]")
            categories: dict[str, list[str]] = {}

            for t in result.tech_stack:
                cat = t.category.title()
                ver = f" (v{t.version})" if t.version else ""
                name = f"{t.name}{ver}"

                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(name)

            for cat, items in categories.items():
                node = tech_tree.add(f"[cyan]{cat}[/cyan]")
                for item in items:
                    node.add(item)

            console.print(tech_tree)
            console.print()

        console.print(f"[dim]Scan completed in {result.duration_ms / 1000:.1f}s[/dim]")

        return "console"

    def _get_grade_color(self, grade: str) -> str:
        if grade.startswith("A"):
            return "green"
        if grade.startswith("B"):
            return "blue"
        if grade.startswith("C"):
            return "yellow"
        if grade.startswith("D"):
            return "dark_orange"
        return "red"

    def _get_priority_color(self, priority: str) -> str:
        if priority == "critical":
            return "bold red"
        if priority == "high":
            return "red"
        if priority == "medium":
            return "yellow"
        return "blue"
