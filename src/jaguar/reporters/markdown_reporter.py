"""
Markdown reporter for JAGUAR.

Generates a human-readable markdown report of the scan results.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import aiofiles

from jaguar.reporters.base import BaseReporter

if TYPE_CHECKING:
    from jaguar.core.models import ScanResult

logger = logging.getLogger("jaguar.reporters.markdown")


class MarkdownReporter(BaseReporter):
    """Generates Markdown reports."""

    name = "markdown"
    format_name = "markdown"

    async def generate(self, result: ScanResult, output_path: str, **options: Any) -> str:
        """Generate markdown and write to file."""
        md = []

        # Header
        md.append(f"# JAGUAR Scan Report: {result.hostname}")
        md.append(f"**URL:** {result.url}  ")

        # Format dates avoiding timezone offset issues if missing
        start_time = result.scan_started_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        md.append(f"**Date:** {start_time}  ")

        md.append(f"**Duration:** {result.duration_ms / 1000:.1f}s")
        md.append("\n---\n")

        # Executive Summary
        md.append("## Executive Summary\n")

        if result.overall_score:
            md.append(
                f"### Overall Grade: {result.overall_score.grade.value} ({result.overall_score.score}/100)\n"
            )
            md.append(f"*{result.overall_score.summary}*\n")

        if result.executive_summary:
            md.append(f"{result.executive_summary}\n")

        md.append("\n---\n")

        # Category Scores
        md.append("## Category Scores\n")
        md.append("| Category | Score | Grade | Summary |")
        md.append("|----------|-------|-------|---------|")

        for name, ar in sorted(result.analyzer_results.items()):
            display_name = name.replace("_", " ").title()
            score = ar.score
            grade = ar.grade.value
            summary = ar.score_explanation.summary
            md.append(f"| {display_name} | {score} | {grade} | {summary} |")

        md.append("\n---\n")

        # AI Recommendations
        if result.recommendations:
            md.append("## Top Recommendations\n")
            for i, rec in enumerate(result.recommendations[:10], 1):
                priority_emoji = {"critical": "🚨", "high": "🔴", "medium": "🟠", "low": "🟡"}.get(
                    rec.priority.value, "ℹ️"
                )

                md.append(f"### {i}. {priority_emoji} {rec.what}")
                md.append(f"**Why:** {rec.why}  ")
                md.append(f"**How to fix:** {rec.how}  ")
                md.append(f"**Impact:** {rec.estimated_impact}\n")

            md.append("\n---\n")

        # Tech Stack & AI Detection
        if result.tech_stack:
            md.append("## Technology Stack\n")
            for tech in result.tech_stack:
                ver = f" (v{tech.version})" if tech.version else ""
                md.append(f"- **{tech.name}**{ver} - *{tech.category.title()}*")
            md.append("\n")

        if result.ai_detection and result.ai_detection.detected_tools:
            md.append("## AI Detection\n")
            md.append(f"Detected Tools: {', '.join(result.ai_detection.detected_tools)}\n")

        md.append("\n---\n")

        # Detailed Findings by Category
        md.append("## Detailed Findings\n")

        for name, ar in sorted(result.analyzer_results.items()):
            display_name = name.replace("_", " ").title()
            md.append(f"### {display_name}\n")

            failed = [f for f in ar.findings if not f.passed]
            passed = [f for f in ar.findings if f.passed]

            if failed:
                md.append("#### Issues\n")
                for f in sorted(failed, key=lambda x: x.severity.value):
                    md.append(f"- ❌ **{f.title}** ({f.severity.value}): {f.description}")

            if passed:
                md.append("#### Passed Checks\n")
                # Only show top 5 passes to avoid clutter
                for f in passed[:5]:
                    md.append(f"- ✅ **{f.title}**: {f.description}")
                if len(passed) > 5:
                    md.append(f"- *...and {len(passed) - 5} more passed checks.*")

            md.append("\n")

        if not output_path.endswith(".md"):
            output_path += ".md"

        content = "\n".join(md)

        try:
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:  # type: ignore
                await f.write(content)  # type: ignore
            logger.info("Markdown report generated at %s", output_path)
            return output_path
        except Exception as e:
            logger.error("Failed to write Markdown report to %s: %s", output_path, e)
            raise
