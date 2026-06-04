"""
Comparison orchestration engine for JAGUAR.

Coordinates comparing two ScanResults and generating competitive insights.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from jaguar.comparator.competitor import generate_competitive_insights
from jaguar.comparator.differ import calculate_scan_deltas
from jaguar.core.models import ComparisonResult, ScanResult

logger = logging.getLogger("jaguar.comparator.engine")


class ComparisonEngine:
    """Orchestrates comparison of two website scans."""

    def compare(self, scan_a: ScanResult, scan_b: ScanResult) -> ComparisonResult:
        """
        Compare two scan results.

        Args:
            scan_a: The baseline scan (e.g. "my site")
            scan_b: The target scan (e.g. "competitor site")

        Returns:
            ComparisonResult containing deltas and insights.
        """
        logger.info("Comparing %s vs %s", scan_a.url, scan_b.url)

        # 1. Calculate numerical and metric deltas
        deltas = calculate_scan_deltas(scan_a, scan_b)

        # 2. Determine overall winner
        overall_winner = None
        overall_score_deltas = [d for d in deltas.get("overall", []) if d.metric == "overall_score"]
        if overall_score_deltas:
            overall_winner = overall_score_deltas[0].winner

        # 3. Create result object
        result = ComparisonResult(
            url_a=scan_a.url,
            url_b=scan_b.url,
            scan_a=scan_a,
            scan_b=scan_b,
            deltas=deltas,
            overall_winner=overall_winner,
            compared_at=datetime.now(UTC),
        )

        # 4. Generate competitive AI insights based on the result
        result.competitive_insights = generate_competitive_insights(result)

        logger.info(
            "Comparison complete. Overall winner: %s",
            "Baseline (A)"
            if overall_winner == "a"
            else "Target (B)"
            if overall_winner == "b"
            else "Tie",
        )

        return result
