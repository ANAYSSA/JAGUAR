"""
Difference calculation engine for JAGUAR.

Requirement #1: Compare websites.
Calculates deltas between two ScanResults, identifying winners
and quantifying differences in scores, metrics, and findings.
"""

from __future__ import annotations

import logging
from typing import Any

from jaguar.core.models import (
    AnalyzerCategory,
    ComparisonDelta,
    ScanResult,
)

logger = logging.getLogger("jaguar.comparator.differ")


def calculate_scan_deltas(
    scan_a: ScanResult, scan_b: ScanResult
) -> dict[str, list[ComparisonDelta]]:
    """
    Calculate differences between two scans across all categories.

    Returns a dictionary mapping category names to lists of ComparisonDeltas.
    """
    deltas: dict[str, list[ComparisonDelta]] = {
        "overall": _compare_overall(scan_a, scan_b),
        "scores": _compare_scores(scan_a, scan_b),
    }

    # Compare specific metrics if analyzers ran on both
    if _both_have(scan_a, scan_b, AnalyzerCategory.PERFORMANCE):
        deltas["performance"] = _compare_performance(scan_a, scan_b)

    if _both_have(scan_a, scan_b, AnalyzerCategory.SEO):
        deltas["seo"] = _compare_seo(scan_a, scan_b)

    if _both_have(scan_a, scan_b, AnalyzerCategory.SECURITY):
        deltas["security"] = _compare_security(scan_a, scan_b)

    return deltas


def _both_have(a: ScanResult, b: ScanResult, category: AnalyzerCategory) -> bool:
    """Check if both scans contain results for a category."""
    return category.value in a.analyzer_results and category.value in b.analyzer_results


def _determine_winner(val_a: float, val_b: float, higher_is_better: bool = True) -> str:
    """Determine the winner between two numeric values."""
    if val_a == val_b:
        return "tie"

    if higher_is_better:
        return "a" if val_a > val_b else "b"
    else:
        return "a" if val_a < val_b else "b"


def _compare_overall(a: ScanResult, b: ScanResult) -> list[ComparisonDelta]:
    """Compare top-level overall metrics."""
    score_a = a.overall_score.score if a.overall_score else 0
    score_b = b.overall_score.score if b.overall_score else 0

    return [
        ComparisonDelta(
            metric="overall_score",
            label="Overall JAGUAR Score",
            value_a=score_a,
            value_b=score_b,
            delta=score_b - score_a,
            winner=_determine_winner(score_a, score_b),
        ),
        ComparisonDelta(
            metric="overall_grade",
            label="Overall Grade",
            value_a=a.overall_score.grade.value if a.overall_score else "N/A",
            value_b=b.overall_score.grade.value if b.overall_score else "N/A",
            winner=_determine_winner(score_a, score_b),
        ),
        ComparisonDelta(
            metric="scan_duration",
            label="Scan Duration (ms)",
            value_a=round(a.duration_ms),
            value_b=round(b.duration_ms),
            delta=round(b.duration_ms - a.duration_ms),
            winner=_determine_winner(a.duration_ms, b.duration_ms, higher_is_better=False),
        ),
    ]


def _compare_scores(a: ScanResult, b: ScanResult) -> list[ComparisonDelta]:
    """Compare all analyzer category scores."""
    deltas = []

    # Get union of all categories run in either scan
    all_categories = set(a.analyzer_results.keys()) | set(b.analyzer_results.keys())

    for cat_name in sorted(list(all_categories)):
        score_a = a.analyzer_results[cat_name].score if cat_name in a.analyzer_results else 0
        score_b = b.analyzer_results[cat_name].score if cat_name in b.analyzer_results else 0

        label = cat_name.replace("_", " ").title() + " Score"

        deltas.append(
            ComparisonDelta(
                metric=f"score_{cat_name}",
                label=label,
                value_a=score_a,
                value_b=score_b,
                delta=score_b - score_a,
                winner=_determine_winner(score_a, score_b),
                explanation=f"A difference of {abs(score_b - score_a)} points in {label}.",
            )
        )

    return deltas


def _compare_performance(a: ScanResult, b: ScanResult) -> list[ComparisonDelta]:
    """Compare specific performance metrics."""
    deltas = []

    perf_a = a.analyzer_results[AnalyzerCategory.PERFORMANCE.value]
    perf_b = b.analyzer_results[AnalyzerCategory.PERFORMANCE.value]

    # Extract page sizes
    size_a = _get_finding_data(perf_a, "page-size", "size_kb", default=0)
    size_b = _get_finding_data(perf_b, "page-size", "size_kb", default=0)

    if size_a or size_b:
        deltas.append(
            ComparisonDelta(
                metric="html_size_kb",
                label="HTML Size (KB)",
                value_a=size_a,
                value_b=size_b,
                delta=size_b - size_a,
                winner=_determine_winner(size_a, size_b, higher_is_better=False),
            )
        )

    # Extract resource counts
    res_a = _get_finding_data(perf_a, "resource-count", "count", default=0)
    res_b = _get_finding_data(perf_b, "resource-count", "count", default=0)

    if res_a or res_b:
        deltas.append(
            ComparisonDelta(
                metric="resource_count",
                label="Total Resources",
                value_a=res_a,
                value_b=res_b,
                delta=res_b - res_a,
                winner=_determine_winner(res_a, res_b, higher_is_better=False),
            )
        )

    return deltas


def _compare_seo(a: ScanResult, b: ScanResult) -> list[ComparisonDelta]:
    """Compare specific SEO metrics."""
    # Count missing essential tags
    seo_a = a.analyzer_results[AnalyzerCategory.SEO.value]
    seo_b = b.analyzer_results[AnalyzerCategory.SEO.value]

    fails_a = sum(1 for f in seo_a.findings if not f.passed)
    fails_b = sum(1 for f in seo_b.findings if not f.passed)

    return [
        ComparisonDelta(
            metric="seo_failures",
            label="SEO Checks Failed",
            value_a=fails_a,
            value_b=fails_b,
            delta=fails_b - fails_a,
            winner=_determine_winner(fails_a, fails_b, higher_is_better=False),
        )
    ]


def _compare_security(a: ScanResult, b: ScanResult) -> list[ComparisonDelta]:
    """Compare specific security metrics."""
    sec_a = a.analyzer_results[AnalyzerCategory.SECURITY.value]
    sec_b = b.analyzer_results[AnalyzerCategory.SECURITY.value]

    # Check HSTS
    hsts_a = _get_finding_data(sec_a, "hsts-implemented", "max_age", default=0)
    hsts_b = _get_finding_data(sec_b, "hsts-implemented", "max_age", default=0)

    return [
        ComparisonDelta(
            metric="hsts_max_age",
            label="HSTS Max-Age (seconds)",
            value_a=hsts_a,
            value_b=hsts_b,
            delta=hsts_b - hsts_a,
            winner=_determine_winner(hsts_a, hsts_b),
        )
    ]


def _get_finding_data(result, partial_name: str, key: str, default: Any = None) -> Any:  # type: ignore
    """Helper to extract a specific data point from a finding."""
    for f in result.findings:
        if partial_name in f.name:
            return f.data.get(key, default)
    return default
