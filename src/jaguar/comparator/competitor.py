"""
Competitor analysis engine for JAGUAR.

Requirement #3: Competitor Analysis Mode.
Generates insights explaining *why* one site is outperforming another
based on the comparison deltas.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jaguar.core.models import ComparisonResult

logger = logging.getLogger("jaguar.comparator.competitor")


def generate_competitive_insights(comparison: ComparisonResult) -> list[str]:
    """
    Generate strategic insights based on comparison deltas.

    Acts as an offline AI generating business-level observations
    comparing the baseline site (a) to the competitor (b).
    """
    insights = []

    # 1. Overall Performance Insight
    overall_deltas = {d.metric: d for d in comparison.deltas.get("overall", [])}
    if "overall_score" in overall_deltas:
        score_delta = overall_deltas["overall_score"]
        if score_delta.winner == "b":
            insights.append(
                f"Competitor ({comparison.url_b}) outperforms your site by {score_delta.delta} points overall. "
                f"They hold a significant advantage in baseline technical quality."
            )
        elif score_delta.winner == "a":
            insights.append(
                f"Your site ({comparison.url_a}) outperforms the competitor by {abs(score_delta.delta)} points overall. "  # type: ignore
                f"You are currently leading in technical quality."
            )
        else:
            insights.append("Both sites have an identical overall technical score.")

    # 2. Category-Specific Insights (Identify biggest gaps)
    score_deltas = comparison.deltas.get("scores", [])

    # Sort deltas by magnitude to find the biggest gaps
    sorted_deltas = sorted(score_deltas, key=lambda x: abs(x.delta or 0), reverse=True)

    for delta in sorted_deltas[:2]:  # Top 2 biggest gaps
        if not delta.delta:
            continue

        category = delta.label.replace(" Score", "")
        if delta.winner == "b":
            insights.append(
                f"WARNING: The competitor has a massive {delta.delta}-point lead in {category}. "
                f"This is your biggest competitive disadvantage and should be prioritized."
            )
        elif delta.winner == "a":
            insights.append(
                f"STRENGTH: You have a commanding {abs(delta.delta)}-point lead in {category}. "
                f"This is a key technical differentiator against this competitor."
            )

    # 3. Specific Metric Insights
    perf_deltas = {d.metric: d for d in comparison.deltas.get("performance", [])}
    if "html_size_kb" in perf_deltas:
        size = perf_deltas["html_size_kb"]
        if size.winner == "b":
            insights.append(
                f"The competitor's page size is {abs(size.delta or 0):.0f} KB lighter than yours, "
                f"giving them an advantage in mobile load times and Core Web Vitals."
            )

    seo_deltas = {d.metric: d for d in comparison.deltas.get("seo", [])}
    if "seo_failures" in seo_deltas:
        fails = seo_deltas["seo_failures"]
        if fails.winner == "b" and (fails.delta or 0) < 0:
            insights.append(
                f"The competitor passes more on-page SEO checks. You have {abs(fails.delta or 0)} more "
                f"SEO issues, which may negatively impact your search rankings relative to them."
            )

    if not insights:
        insights.append("The sites are too similar to extract meaningful competitive insights.")

    return insights
