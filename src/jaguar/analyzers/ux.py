"""
User Experience (UX) analyzer for JAGUAR.

Evaluates readability, navigation, CTAs, trust indicators, and mobile-friendliness.
Relies on Playwright DOM analysis scripts and text utils.
"""

from __future__ import annotations

import logging

from jaguar.analyzers.base import BaseAnalyzer
from jaguar.core.models import AnalyzerCategory, Finding, ScanContext, Severity
from jaguar.utils.text import extract_visible_text, flesch_reading_ease

logger = logging.getLogger("jaguar.analyzers.ux")


class UXAnalyzer(BaseAnalyzer):
    """User Experience (UX) analyzer."""

    name = "ux"
    category = AnalyzerCategory.UX
    weight = 1.0

    async def _run_checks(self, context: ScanContext) -> list[Finding]:
        findings: list[Finding] = []

        # 1. Readability analysis (can be done without browser)
        text = extract_visible_text(context.response_body)
        findings.append(self._check_readability(text))

        # 2. DOM structural analysis (needs browser)
        if context.browser_available:
            dom_findings = await self._run_dom_analysis(context)
            findings.extend(dom_findings)
        else:
            findings.append(
                Finding(
                    name="ux-dom-skipped",
                    title="UX DOM Analysis Skipped",
                    description="Playwright browser is not available. Deep UX analysis skipped.",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=0,
                )
            )

        return findings

    def _check_readability(self, text: str) -> Finding:
        if not text.strip():
            return Finding(
                name="no-text-content",
                title="No Text Content",
                description="Insufficient text content to analyze readability.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )

        score = flesch_reading_ease(text)

        if score >= 60:
            return Finding(
                name="good-readability",
                title="Good Readability",
                description=f"Flesch Reading Ease score is {score:.1f}. Content is accessible to a broad audience.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=5,
                data={"flesch_score": score},
            )
        elif score >= 45:
            return Finding(
                name="fair-readability",
                title="Fair Readability",
                description=f"Flesch Reading Ease score is {score:.1f}. Content is moderately difficult.",
                passed=False,
                severity=Severity.LOW,
                score_modifier=-5,
                data={"flesch_score": score},
                recommendation="Consider simplifying text structure to improve comprehension.",
            )
        else:
            return Finding(
                name="poor-readability",
                title="Poor Readability",
                description=f"Flesch Reading Ease score is {score:.1f}. Content is very difficult to read.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-15,
                data={"flesch_score": score},
                recommendation="Use shorter sentences, simpler words, and clear formatting to improve UX.",
            )

    async def _run_dom_analysis(self, ctx: ScanContext) -> list[Finding]:
        findings: list[Finding] = []

        try:
            from jaguar.browser.manager import BrowserManager
            from jaguar.browser.scripts import DOM_ANALYSIS_SCRIPT

            browser = BrowserManager(headless=ctx.config.get("browser", {}).get("headless", True))
            page = await browser.new_page()

            try:
                await browser.navigate_and_wait(page, ctx.url)
                results = await browser.inject_script(page, DOM_ANALYSIS_SCRIPT)

                # Navigation
                nav = results.get("navigation", {})
                if not nav.get("hasMainNav"):
                    findings.append(
                        Finding(
                            name="missing-main-nav",
                            title="Missing Main Navigation",
                            description="No <nav> or role='navigation' elements found.",
                            passed=False,
                            severity=Severity.HIGH,
                            score_modifier=-15,
                            recommendation="Implement clear, semantic navigation to help users orient themselves.",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            name="has-main-nav",
                            title="Navigation Structure OK",
                            description=f"Found {nav.get('navElementCount')} navigation elements.",
                            passed=True,
                            severity=Severity.INFO,
                            score_modifier=5,
                        )
                    )

                # CTAs
                ctas = results.get("ctas", {})
                if ctas.get("count", 0) == 0:
                    findings.append(
                        Finding(
                            name="missing-ctas",
                            title="No Call-to-Action Elements",
                            description="No obvious button or CTA elements found on the page.",
                            passed=False,
                            severity=Severity.MEDIUM,
                            score_modifier=-10,
                            recommendation="Add clear Call-to-Action (CTA) elements to guide user journeys.",
                        )
                    )
                elif ctas.get("aboveFold", 0) == 0:
                    findings.append(
                        Finding(
                            name="no-above-fold-cta",
                            title="No CTAs Above the Fold",
                            description="CTAs are present but require scrolling to see.",
                            passed=False,
                            severity=Severity.LOW,
                            score_modifier=-5,
                            recommendation="Place at least one primary CTA above the fold for immediate visibility.",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            name="ctas-ok",
                            title="Call-to-Action Elements Present",
                            description=f"Found {ctas.get('count')} CTAs, {ctas.get('aboveFold')} above the fold.",
                            passed=True,
                            severity=Severity.INFO,
                            score_modifier=5,
                        )
                    )

                # Trust Indicators
                trust = results.get("trust", {})
                trust_score = sum(
                    [
                        trust.get("hasPrivacyPolicy", False),
                        trust.get("hasTerms", False),
                        trust.get("hasContact", False),
                        trust.get("hasSocialLinks", False),
                        trust.get("hasHttps", False),
                    ]
                )

                if trust_score < 3:
                    findings.append(
                        Finding(
                            name="low-trust-signals",
                            title="Low Trust Signals",
                            description=f"Only {trust_score}/5 basic trust indicators found (privacy, terms, contact, social, https).",
                            passed=False,
                            severity=Severity.MEDIUM,
                            score_modifier=-10,
                            recommendation="Add clear links to Privacy Policy, Terms, and Contact information in the footer.",
                        )
                    )
                else:
                    findings.append(
                        Finding(
                            name="good-trust-signals",
                            title="Good Trust Signals",
                            description=f"Found {trust_score}/5 basic trust indicators.",
                            passed=True,
                            severity=Severity.INFO,
                            score_modifier=5,
                        )
                    )

            finally:
                await page.close()

        except Exception as e:
            logger.debug("UX DOM analysis failed: %s", e)

        return findings
