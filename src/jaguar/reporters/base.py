"""
Base class for JAGUAR reporters.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jaguar.core.models import ScanResult

logger = logging.getLogger("jaguar.reporters")


class BaseReporter(ABC):
    """
    Abstract base class for reporters.

    Reporters format and output ScanResults.
    """

    name: str = "unnamed-reporter"
    format_name: str = "unknown"

    @abstractmethod
    async def generate(self, result: ScanResult, output_path: str, **options: Any) -> str:
        """
        Generate the report.

        Args:
            result: The scan result to report on
            output_path: Where to write the report (if applicable)
            options: Reporter-specific options

        Returns:
            String path to the generated report, or the report content itself
            depending on the reporter.
        """
        ...
