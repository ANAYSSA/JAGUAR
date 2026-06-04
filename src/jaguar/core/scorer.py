"""
Unified scoring and grading system for JAGUAR.

Every analyzer produces a 0-100 score. This module:
- Converts numeric scores to letter grades (A+ through F)
- Generates score explanations (what reduced / could increase score)
- Computes weighted overall scores across multiple analyzers
- Provides the scoring decorator for individual checks

Inspired by Mozilla HTTP Observatory's grading system but generalized
to work across all JAGUAR analyzer categories.
"""

from __future__ import annotations

from jaguar.core.models import (
    AnalyzerCategory,
    Finding,
    Grade,
    ScoreExplanation,
)

# ---------------------------------------------------------------------------
# Grade chart: score threshold → letter grade
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS: list[tuple[int, Grade]] = [
    (97, Grade.A_PLUS),
    (93, Grade.A),
    (90, Grade.A_MINUS),
    (87, Grade.B_PLUS),
    (83, Grade.B),
    (80, Grade.B_MINUS),
    (77, Grade.C_PLUS),
    (73, Grade.C),
    (70, Grade.C_MINUS),
    (67, Grade.D_PLUS),
    (63, Grade.D),
    (60, Grade.D_MINUS),
    (0, Grade.F),
]

# Default weights for overall score computation
DEFAULT_WEIGHTS: dict[AnalyzerCategory, float] = {
    AnalyzerCategory.SECURITY: 1.5,
    AnalyzerCategory.SECRETS: 1.3,
    AnalyzerCategory.SEO: 1.0,
    AnalyzerCategory.PERFORMANCE: 1.2,
    AnalyzerCategory.ACCESSIBILITY: 1.1,
    AnalyzerCategory.TECHSTACK: 0.3,
    AnalyzerCategory.UX: 1.0,
    AnalyzerCategory.AI_DESIGN: 0.7,
    AnalyzerCategory.AI_DETECT: 0.4,
    AnalyzerCategory.VULNERABILITY: 1.4,
}


def score_to_grade(score: int) -> Grade:
    """Convert a numeric 0-100 score to a letter grade."""
    clamped = max(0, min(100, score))
    for threshold, grade in _GRADE_THRESHOLDS:
        if clamped >= threshold:
            return grade
    return Grade.F


def compute_analyzer_score(findings: list[Finding], base_score: int = 100) -> int:
    """
    Compute an analyzer's score from its findings.

    Starts at `base_score` and applies each finding's score_modifier.
    The result is clamped to [0, 100].
    """
    score = base_score
    for finding in findings:
        score += finding.score_modifier
    return max(0, min(100, score))


def build_score_explanation(
    findings: list[Finding],
    score: int,
    analyzer_name: str,
) -> ScoreExplanation:
    """
    Build a full score explanation from findings.

    Requirement #7: every score must explain why it was given,
    what reduced the score, and what could increase it.
    """
    grade = score_to_grade(score)

    penalties: list[str] = []
    bonuses: list[str] = []
    improvements: list[str] = []

    for f in findings:
        if f.score_modifier < 0:
            penalties.append(f"{f.title}: {f.score_modifier} pts — {f.description}")
        elif f.score_modifier > 0:
            bonuses.append(f"{f.title}: +{f.score_modifier} pts — {f.description}")

        if not f.passed and f.recommendation:
            impact = abs(f.score_modifier) if f.score_modifier < 0 else 5
            improvements.append(f"{f.recommendation} (potential +{impact} pts)")

    if score >= 97:
        summary = f"{analyzer_name} is excellent — virtually all checks passed."
    elif score >= 90:
        summary = f"{analyzer_name} is very good with minor issues."
    elif score >= 80:
        summary = f"{analyzer_name} is good but has some areas for improvement."
    elif score >= 70:
        summary = f"{analyzer_name} is acceptable but needs attention."
    elif score >= 60:
        summary = f"{analyzer_name} has significant issues that should be addressed."
    else:
        summary = f"{analyzer_name} has critical issues requiring immediate attention."

    return ScoreExplanation(
        score=score,
        grade=grade,
        summary=summary,
        penalties=penalties,
        bonuses=bonuses,
        improvements=improvements,
    )


def compute_overall_score(
    category_scores: dict[AnalyzerCategory, int],
    weights: dict[AnalyzerCategory, float] | None = None,
) -> ScoreExplanation:
    """
    Compute a weighted overall score across all analyzer categories.

    Categories not present in `category_scores` are simply omitted
    from the weighted average (they don't drag the score down).
    """
    w = weights or DEFAULT_WEIGHTS

    total_weight = 0.0
    weighted_sum = 0.0
    penalties: list[str] = []
    bonuses: list[str] = []
    improvements: list[str] = []

    for category, score in category_scores.items():
        weight = w.get(category, 1.0)
        total_weight += weight
        weighted_sum += score * weight

        label = category.value.replace("_", " ").title()
        if score < 60:
            penalties.append(f"{label} scored {score}/100 — critical weakness")
        elif score < 80:
            penalties.append(f"{label} scored {score}/100 — needs improvement")
        elif score >= 95:
            bonuses.append(f"{label} scored {score}/100 — excellent")

        if score < 90:
            gap = 90 - score
            improvements.append(f"Improve {label} by {gap} points to reach A- level")

    overall = 0 if total_weight == 0 else int(round(weighted_sum / total_weight))

    overall = max(0, min(100, overall))
    grade = score_to_grade(overall)

    return ScoreExplanation(
        score=overall,
        grade=grade,
        summary=_overall_summary(overall, len(category_scores)),
        penalties=penalties,
        bonuses=bonuses,
        improvements=improvements,
    )


def _overall_summary(score: int, num_categories: int) -> str:
    """Generate a human-readable overall summary."""
    if num_categories == 0:
        return "No analyzers were run."
    if score >= 95:
        return "Outstanding website — excels across all analyzed dimensions."
    if score >= 85:
        return "Very good website with only minor issues to address."
    if score >= 75:
        return "Good website overall, but several areas need improvement."
    if score >= 65:
        return "Average website — multiple areas require attention."
    if score >= 50:
        return "Below average — significant improvements needed across multiple areas."
    return "Poor website quality — critical issues found in most areas."
