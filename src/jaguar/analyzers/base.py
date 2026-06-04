"""
Base analyzer class for JAGUAR.

All analyzers inherit from BaseAnalyzer which provides:
- Consistent interface via the AnalyzerProtocol
- Score computation from findings
- Score explanation generation
- Recommendation attachment
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from jaguar.core.models import (
    AnalyzerCategory,
    AnalyzerResult,
    Finding,
    ScanContext,
)
from jaguar.core.scorer import build_score_explanation, compute_analyzer_score

logger = logging.getLogger("jaguar.analyzers")


class BaseAnalyzer(ABC):
    """
    Abstract base class for all JAGUAR analyzers.

    Subclasses must implement:
    - name: str
    - category: AnalyzerCategory
    - _run_checks(context) -> list[Finding]

    The base class handles score computation, explanation generation,
    and result packaging automatically.
    """

    name: str = "unnamed"
    category: AnalyzerCategory = AnalyzerCategory.SECURITY
    weight: float = 1.0
    base_score: int = 100

    @abstractmethod
    async def _run_checks(self, context: ScanContext) -> list[Finding]:
        """
        Run all checks for this analyzer.

        Returns a list of Finding objects, each representing
        one discrete test or observation.
        """
        ...

    async def analyze(self, context: ScanContext) -> AnalyzerResult:
        """
        Execute the analyzer and return a scored result.

        This is the main entry point called by the engine.
        Do not override this — override _run_checks instead.
        """
        start = time.monotonic()

        findings = await self._run_checks(context)

        # Compute score
        score = compute_analyzer_score(findings, self.base_score)

        # Build explanation
        explanation = build_score_explanation(findings, score, self.display_name)

        elapsed = (time.monotonic() - start) * 1000

        return AnalyzerResult(
            analyzer_name=self.name,
            category=self.category,
            findings=findings,
            score_explanation=explanation,
            duration_ms=elapsed,
        )

    @property
    def display_name(self) -> str:
        """Human-readable name for this analyzer."""
        return self.name.replace("_", " ").title()
