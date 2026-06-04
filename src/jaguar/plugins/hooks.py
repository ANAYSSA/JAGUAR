"""
Plugin lifecycle hooks for JAGUAR.

Hooks allow plugins to intercept the scan lifecycle at key points
without modifying core code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jaguar.core.plugin import BaseHook

if TYPE_CHECKING:
    from jaguar.core.models import ScanContext, ScanResult


class LoggingHook(BaseHook):
    """Example built-in hook that logs scan lifecycle events."""

    name = "logging"

    async def pre_scan(self, context: ScanContext) -> ScanContext:
        import logging

        logging.getLogger("jaguar.hook.logging").info("Scan starting: %s", context.url)
        return context

    async def post_scan(self, result: ScanResult) -> ScanResult:
        import logging

        score = result.overall_score.score if result.overall_score else "N/A"
        logging.getLogger("jaguar.hook.logging").info(
            "Scan complete: %s — Score: %s", result.url, score
        )
        return result
