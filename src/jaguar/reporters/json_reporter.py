"""
JSON reporter for JAGUAR.

Outputs the full ScanResult model as a formatted JSON file.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import aiofiles

from jaguar.reporters.base import BaseReporter

if TYPE_CHECKING:
    from jaguar.core.models import ScanResult

logger = logging.getLogger("jaguar.reporters.json")


class JsonReporter(BaseReporter):
    """Generates JSON reports."""

    name = "json"
    format_name = "json"

    async def generate(self, result: ScanResult, output_path: str, **options: Any) -> str:
        """Serialize the ScanResult to JSON and write to file."""
        json_str = result.model_dump_json(indent=2)

        if not output_path.endswith(".json"):
            output_path += ".json"

        try:
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(json_str)
            logger.info("JSON report generated at %s", output_path)
            return output_path
        except Exception as e:
            logger.error("Failed to write JSON report to %s: %s", output_path, e)
            raise
