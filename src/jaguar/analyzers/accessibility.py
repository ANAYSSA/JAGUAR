"""
Accessibility analyzer for JAGUAR.

Runs axe-core rules via Playwright to detect WCAG violations.
Requires the browser to be available.
"""

from __future__ import annotations

import logging
from typing import Any

from jaguar.analyzers.base import BaseAnalyzer
from jaguar.core.models import AnalyzerCategory, Finding, ScanContext, Severity

logger = logging.getLogger("jaguar.analyzers.accessibility")


class AccessibilityAnalyzer(BaseAnalyzer):
    """WCAG accessibility analyzer using axe-core."""

    name = "accessibility"
    category = AnalyzerCategory.ACCESSIBILITY
    weight = 1.1

    async def _run_checks(self, context: ScanContext) -> list[Finding]:
        if not context.browser_available:
            return [
                Finding(
                    name="browser-unavailable",
                    title="Accessibility Tests Skipped",
                    description="Playwright browser is not available. Accessibility tests require a full browser environment to render the page.",
                    passed=True,  # Don't penalize if browser is simply missing
                    severity=Severity.INFO,
                    score_modifier=0,
                )
            ]

        try:
            from jaguar.browser.manager import BrowserManager
            from jaguar.browser.scripts import AXE_CORE_CDN, AXE_RUN_SCRIPT

            browser = BrowserManager(
                headless=context.config.get("browser", {}).get("headless", True)
            )
            page = await browser.new_page()

            try:
                await browser.navigate_and_wait(page, context.url)

                # Inject axe-core from CDN
                await page.add_script_tag(url=AXE_CORE_CDN)

                # Wait a tiny bit for it to initialize
                await page.wait_for_timeout(500)

                # Run the runner script
                results = await browser.inject_script(page, AXE_RUN_SCRIPT)

                if "error" in results:
                    logger.warning("axe-core error: %s", results["error"])
                    return [
                        Finding(
                            name="axe-core-failed",
                            title="Accessibility Scan Failed",
                            description=f"Could not run axe-core: {results['error']}",
                            passed=False,
                            severity=Severity.MEDIUM,
                            score_modifier=-5,
                        )
                    ]

                return self._parse_axe_results(results)

            finally:
                await page.close()

        except ImportError:
            return [
                Finding(
                    name="playwright-missing",
                    title="Playwright Not Installed",
                    description="Install JAGUAR with 'browser' extra to run accessibility tests.",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=0,
                )
            ]
        except Exception as e:
            logger.error("Accessibility scan failed: %s", e)
            return [
                Finding(
                    name="accessibility-scan-error",
                    title="Accessibility Scan Error",
                    description=str(e),
                    passed=False,
                    severity=Severity.LOW,
                    score_modifier=0,
                )
            ]

    def _parse_axe_results(self, results: dict[str, Any]) -> list[Finding]:
        """Convert axe-core results into findings."""
        findings: list[Finding] = []
        violations = results.get("violations", [])

        if not violations:
            findings.append(
                Finding(
                    name="no-wcag-violations",
                    title="No Accessibility Violations Found",
                    description="axe-core found no WCAG violations on this page.",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=0,
                    data={"passes": results.get("passes", 0)},
                )
            )
            return findings

        severity_map = {
            "critical": Severity.CRITICAL,
            "serious": Severity.HIGH,
            "moderate": Severity.MEDIUM,
            "minor": Severity.LOW,
        }

        modifier_map = {
            "critical": -10,
            "serious": -5,
            "moderate": -3,
            "minor": -1,
        }

        for violation in violations:
            impact = violation.get("impact", "minor")
            node_count = violation.get("nodes", 1)

            # Cap the penalty per violation type
            base_modifier = modifier_map.get(impact, -1)
            # -10 for the rule, plus a bit for each occurrence, max double base
            total_modifier = max(base_modifier * 2, base_modifier - (node_count - 1))

            findings.append(
                Finding(
                    name=f"axe-{violation.get('id', 'unknown')}",
                    title=f"WCAG Violation: {violation.get('help', 'Unknown')}",
                    description=f"{violation.get('description', '')}. Affects {node_count} element(s).",
                    passed=False,
                    severity=severity_map.get(impact, Severity.INFO),
                    score_modifier=total_modifier,
                    recommendation=f"Review documentation: {violation.get('helpUrl', '')}",
                    data={"tags": violation.get("tags", []), "impact": impact, "nodes": node_count},
                )
            )

        return findings
