"""
AI Detection analyzer for JAGUAR.

Requirement #4: Detect Lovable, Bolt, v0, Replit, Cursor, Claude Code,
GPT-generated patterns, Shadcn/UI templates, AI-generated text.

Uses browser-injected DOM analysis scripts and text analysis heuristics.
"""

from __future__ import annotations

import logging
from typing import Any

from jaguar.analyzers.base import BaseAnalyzer
from jaguar.core.models import AnalyzerCategory, Finding, ScanContext, Severity
from jaguar.utils.text import detect_boilerplate_ratio, extract_visible_text

logger = logging.getLogger("jaguar.analyzers.ai_detect")


class AIDetectAnalyzer(BaseAnalyzer):
    """Detects AI-generated content and AI site builders."""

    name = "ai_detect"
    category = AnalyzerCategory.AI_DETECT
    weight = 0.4

    async def _run_checks(self, context: ScanContext) -> list[Finding]:
        findings: list[Finding] = []

        # Text analysis (offline heuristics)
        text = extract_visible_text(context.response_body)
        findings.append(self._check_ai_text(text))

        # Tool detection (needs browser)
        ai_data: dict[str, Any] = {}
        if context.browser_available:
            tool_findings, ai_data = await self._run_tool_detection(context)
            findings.extend(tool_findings)
        else:
            findings.append(
                Finding(
                    name="ai-detect-skipped",
                    title="Deep AI Detection Skipped",
                    description="Playwright browser is not available. Deep AI tool detection skipped.",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=0,
                )
            )

        # We attach the raw ai_data to one of the findings so the engine can extract it
        if findings:
            findings[0].data["ai_detection"] = ai_data

        return findings

    def _check_ai_text(self, text: str) -> Finding:
        if not text.strip():
            return Finding(
                name="no-text-for-ai",
                title="AI Text Detection",
                description="Not enough text to analyze.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )

        boilerplate_ratio = detect_boilerplate_ratio(text)

        if boilerplate_ratio > 0.6:
            return Finding(
                name="high-ai-text-probability",
                title="High Probability of AI Text",
                description="Text contains many generic phrases common in AI generation.",
                passed=False,
                severity=Severity.LOW,
                score_modifier=-15,
                data={"boilerplate_ratio": boilerplate_ratio},
            )
        elif boilerplate_ratio > 0.3:
            return Finding(
                name="moderate-ai-text-probability",
                title="Moderate Probability of AI Text",
                description="Text contains some generic boilerplate phrases.",
                passed=False,
                severity=Severity.LOW,
                score_modifier=-5,
                data={"boilerplate_ratio": boilerplate_ratio},
            )

        return Finding(
            name="low-ai-text-probability",
            title="Low Probability of AI Text",
            description="Text does not strongly exhibit AI boilerplate patterns.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={"boilerplate_ratio": boilerplate_ratio},
        )

    async def _run_tool_detection(self, ctx: ScanContext) -> tuple[list[Finding], dict[str, Any]]:
        findings: list[Finding] = []

        ai_data = {
            "design_ai_probability": 0.0,
            "code_ai_probability": 0.0,
            "text_ai_probability": 0.0,
            "detected_tools": [],
            "tool_confidences": {},
            "evidence": {},
        }

        try:
            from jaguar.browser.manager import BrowserManager
            from jaguar.browser.scripts import AI_TOOL_DETECT_SCRIPT

            browser = BrowserManager(headless=ctx.config.get("browser", {}).get("headless", True))
            page = await browser.new_page()

            try:
                await browser.navigate_and_wait(page, ctx.url)
                signals = await browser.inject_script(page, AI_TOOL_DETECT_SCRIPT)

                # Process signals
                tools_detected = []

                if signals.get("lovable", {}).get("metaGenerator") or signals.get(
                    "lovable", {}
                ).get("classPatterns"):
                    tools_detected.append("Lovable")
                    ai_data["tool_confidences"]["Lovable"] = 0.9  # type: ignore

                if signals.get("bolt", {}).get("boltMeta") or signals.get("bolt", {}).get(
                    "stackblitzEmbed"
                ):
                    tools_detected.append("Bolt.new")
                    ai_data["tool_confidences"]["Bolt.new"] = 0.9  # type: ignore

                if signals.get("v0", {}).get("comments") or signals.get("v0", {}).get(
                    "shadcnPatterns"
                ):
                    tools_detected.append("v0.dev")
                    ai_data["tool_confidences"]["v0.dev"] = 0.8  # type: ignore

                if signals.get("replit", {}).get("replitBadge") or signals.get("replit", {}).get(
                    "meta"
                ):
                    tools_detected.append("Replit")
                    ai_data["tool_confidences"]["Replit"] = 0.9  # type: ignore

                if signals.get("shadcnUI", {}).get("dataSlots") > 0 and signals.get(
                    "shadcnUI", {}
                ).get("radixPrimitives"):
                    tools_detected.append("shadcn/ui")
                    ai_data["tool_confidences"]["shadcn/ui"] = 0.85  # type: ignore

                code_patterns = signals.get("codePatterns", {})
                if code_patterns.get("excessiveComments") and code_patterns.get("genericVarNames"):
                    tools_detected.append("Cursor/Claude Code")
                    ai_data["tool_confidences"]["Cursor/Claude Code"] = 0.6  # type: ignore

                if tools_detected:
                    findings.append(
                        Finding(
                            name="ai-tools-detected",
                            title="AI Generation Tools Detected",
                            description=f"Detected signatures of: {', '.join(tools_detected)}.",
                            passed=False,
                            severity=Severity.INFO,
                            score_modifier=-10,  # Just informational/minor penalty
                            data={"tools": tools_detected},
                        )
                    )
                    ai_data["detected_tools"] = tools_detected
                    ai_data["code_ai_probability"] = 85.0
                else:
                    findings.append(
                        Finding(
                            name="no-ai-tools",
                            title="No AI Tools Detected",
                            description="Did not detect explicit signatures of AI site builders.",
                            passed=True,
                            severity=Severity.INFO,
                            score_modifier=0,
                        )
                    )

            finally:
                await page.close()

        except Exception as e:
            logger.debug("AI tool detection failed: %s", e)

        return findings, ai_data
