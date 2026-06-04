"""
AI Design analyzer for JAGUAR.

Detects AI-generated design patterns such as:
- Common template structures
- Repetitive layouts
- Default color palettes often used by AI generators
"""

from __future__ import annotations

import logging
import re

from jaguar.analyzers.base import BaseAnalyzer
from jaguar.core.models import AnalyzerCategory, Finding, ScanContext, Severity

logger = logging.getLogger("jaguar.analyzers.ai_design")


class AIDesignAnalyzer(BaseAnalyzer):
    """Detects AI-generated design patterns."""

    name = "ai_design"
    category = AnalyzerCategory.AI_DESIGN
    weight = 0.7

    async def _run_checks(self, context: ScanContext) -> list[Finding]:
        findings: list[Finding] = []

        html = context.response_body

        # Check for generic boilerplate sections
        findings.append(self._check_boilerplate_structure(html))

        # Check for generic classes (like "container", "hero", "features")
        findings.append(self._check_generic_classes(html))

        return findings

    def _check_boilerplate_structure(self, html: str) -> Finding:
        # Looking for classic AI-generated hero -> features -> cta -> footer flow
        has_hero = bool(
            re.search(r'class=["\'][^"\']*\b(hero|header-banner)\b', html, re.IGNORECASE)
        )
        has_features = bool(
            re.search(r'class=["\'][^"\']*\b(features|services-grid)\b', html, re.IGNORECASE)
        )
        has_cta = bool(
            re.search(r'class=["\'][^"\']*\b(cta|call-to-action|newsletter)\b', html, re.IGNORECASE)
        )

        score = sum([has_hero, has_features, has_cta])

        if score == 3:
            return Finding(
                name="generic-page-structure",
                title="Generic Page Structure Detected",
                description="The page follows a very common, potentially templated or AI-generated structure (Hero -> Features -> CTA).",
                passed=False,
                severity=Severity.LOW,
                score_modifier=-10,
                recommendation="Differentiate your design from generic templates to improve brand identity.",
            )

        return Finding(
            name="custom-page-structure",
            title="Custom Page Structure",
            description="Page structure does not strongly match generic boilerplate patterns.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
        )

    def _check_generic_classes(self, html: str) -> Finding:
        # Check for over-reliance on generic utility classes
        classes = re.findall(r'class=["\']([^"\']+)["\']', html)
        all_classes = " ".join(classes).split()

        generic_terms = {"container", "wrapper", "inner", "content", "box", "row", "col", "item"}
        generic_count = sum(1 for c in all_classes if c.lower() in generic_terms)

        if len(all_classes) > 0 and (generic_count / len(all_classes)) > 0.3:
            return Finding(
                name="high-generic-classes",
                title="High Reliance on Generic CSS Classes",
                description="Over 30% of CSS classes are generic structural terms (e.g., container, wrapper).",
                passed=False,
                severity=Severity.LOW,
                score_modifier=-5,
            )

        return Finding(
            name="css-classes-ok",
            title="CSS Class Naming OK",
            description="CSS class naming appears sufficiently specific.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
        )
