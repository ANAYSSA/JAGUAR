"""
HTML reporter for JAGUAR.

Generates a standalone HTML report with charts and interactive tables
using Jinja2 templates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from jaguar.reporters.base import BaseReporter

if TYPE_CHECKING:
    from jaguar.core.models import ScanResult

logger = logging.getLogger("jaguar.reporters.html")


class HtmlReporter(BaseReporter):
    """Generates standalone HTML reports."""

    name = "html"
    format_name = "html"

    async def generate(self, result: ScanResult, output_path: str, **options: Any) -> str:
        """Generate HTML and write to file."""
        if not output_path.endswith(".html"):
            output_path += ".html"

        # Setup Jinja environment
        template_dir = Path(__file__).parent.parent / "data"
        env = Environment(
            loader=FileSystemLoader(template_dir), autoescape=select_autoescape(["html", "xml"])
        )

        try:
            template = env.get_template("report_template.html")

            # Serialize result to dict for template access
            data = result.model_dump(mode="json")

            # Prepare JSON string for chart data
            chart_data = {
                "categories": list(data.get("analyzer_results", {}).keys()),
                "scores": [
                    ar.get("score_explanation", {}).get("score", 0)
                    for ar in data.get("analyzer_results", {}).values()
                ],
            }

            html_content = template.render(result=data, chart_data=json.dumps(chart_data))

            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(html_content)

            logger.info("HTML report generated at %s", output_path)
            return output_path

        except Exception as e:
            logger.error("Failed to generate HTML report: %s", e)
            # If template fails, fallback to very basic HTML
            return await self._generate_fallback(result, output_path)

    async def _generate_fallback(self, result: ScanResult, output_path: str) -> str:
        """Fallback basic HTML generation if Jinja template is missing."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>JAGUAR Scan: {result.hostname}</title>
    <style>body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}</style>
</head>
<body>
    <h1>JAGUAR Scan Report: {result.hostname}</h1>
    <p><strong>URL:</strong> <a href="{result.url}">{result.url}</a></p>
    <p><strong>Overall Score:</strong> {result.overall_score.score if result.overall_score else "N/A"}/100</p>
    <hr>
    <p>Note: This is a fallback report because the HTML template was not found.</p>
</body>
</html>"""

        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            await f.write(html)

        return output_path
