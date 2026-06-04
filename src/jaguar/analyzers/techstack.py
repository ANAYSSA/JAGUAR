"""
Technology stack fingerprinting analyzer for JAGUAR.

Detects frameworks, libraries, CMS, and servers by analyzing:
- HTTP headers (Server, X-Powered-By)
- HTML patterns (meta tags, DOM structures)
- JavaScript globals (via browser injection if available)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from jaguar.analyzers.base import BaseAnalyzer
from jaguar.core.models import AnalyzerCategory, Finding, ScanContext, Severity

logger = logging.getLogger("jaguar.analyzers.techstack")

# Basic header signatures
HEADER_SIGNATURES = {
    "Server": {
        r"nginx": "Nginx",
        r"apache": "Apache",
        r"cloudflare": "Cloudflare",
        r"express": "Express.js",
        r"caddy": "Caddy",
        r"gunicorn": "Gunicorn",
        r"uvicorn": "Uvicorn",
        r"werkzeug": "Werkzeug (Python)",
    },
    "X-Powered-By": {
        r"php": "PHP",
        r"express": "Express.js",
        r"next\.js": "Next.js",
        r"asp\.net": "ASP.NET",
        r"rails": "Ruby on Rails",
        r"sails": "Sails.js",
        r"nuxt": "Nuxt.js",
    },
    "X-Generator": {
        r"drupal": "Drupal",
        r"wordpress": "WordPress",
        r"joomla": "Joomla",
    },
}


class TechStackAnalyzer(BaseAnalyzer):
    """Detects technologies used to build the website."""

    name = "techstack"
    category = AnalyzerCategory.TECHSTACK
    weight = 0.3  # Low weight for overall score (informational)

    async def _run_checks(self, context: ScanContext) -> list[Finding]:
        findings: list[Finding] = []
        detections: list[dict[str, Any]] = []
        found_names: set[str] = set()

        # 1. Analyze HTTP Headers
        header_dets = self._analyze_headers(context.response_headers)
        for d in header_dets:
            if d["name"] not in found_names:
                detections.append(d)
                found_names.add(d["name"])

        # 2. Analyze HTML Source
        html_dets = self._analyze_html(context.response_body)
        for d in html_dets:
            if d["name"] not in found_names:
                detections.append(d)
                found_names.add(d["name"])

        # 3. Analyze via JavaScript (if browser available)
        if context.browser_available:
            js_dets = await self._analyze_via_js(context)
            for d in js_dets:
                # Merge logic if already found
                if d["name"] in found_names:
                    # Update version or confidence if better
                    pass
                else:
                    detections.append(d)
                    found_names.add(d["name"])

        # Create finding with all detections
        if detections:
            desc_parts = [f"{d['name']} ({d['category']})" for d in detections]
            findings.append(
                Finding(
                    name="tech-stack-detected",
                    title="Technology Stack Detected",
                    description=f"Detected {len(detections)} technologies: {', '.join(desc_parts[:10])}",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=0,
                    data={"detections": detections},
                )
            )

            # Security check: Are headers exposing too much version info?
            version_exposures = []
            for h in ["Server", "X-Powered-By"]:
                val = context.response_headers.get(h, "")
                if re.search(r"\d+\.\d+", val):
                    version_exposures.append(f"{h}: {val}")

            if version_exposures:
                findings.append(
                    Finding(
                        name="version-exposure",
                        title="Software Version Exposed",
                        description="HTTP headers expose specific software versions, which aids attackers in finding known vulnerabilities.",
                        passed=False,
                        severity=Severity.LOW,
                        score_modifier=-5,
                        data={"exposures": version_exposures},
                        recommendation="Configure your server/framework to hide exact version numbers in HTTP headers.",
                    )
                )
        else:
            findings.append(
                Finding(
                    name="tech-stack-unknown",
                    title="Technology Stack Unknown",
                    description="Could not fingerprint the underlying technologies.",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=0,
                )
            )

        return findings

    def _analyze_headers(self, headers: dict[str, str]) -> list[dict[str, Any]]:
        detections: list[dict[str, Any]] = []

        for header, rules in HEADER_SIGNATURES.items():
            value = headers.get(header, "").lower()
            if not value:
                continue

            for pattern, name in rules.items():
                if re.search(pattern, value):
                    version = None
                    # Try to extract version e.g. "nginx/1.18.0" -> "1.18.0"
                    version_match = re.search(r"[\/\s](\d+\.\d+(?:\.\d+)?)", value)
                    if version_match:
                        version = version_match.group(1)

                    detections.append(
                        {
                            "name": name,
                            "category": "server" if header == "Server" else "framework",
                            "version": version,
                            "confidence": 0.9,
                            "evidence": [f"{header}: {value}"],
                        }
                    )

        return detections

    def _analyze_html(self, html: str) -> list[dict[str, Any]]:
        detections: list[dict[str, Any]] = []

        # Generator meta tags
        match = re.search(
            r'<meta\s+name=["\']generator["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE
        )
        if match:
            gen = match.group(1)
            name = gen
            version = None
            if " " in gen:
                parts = gen.split(" ", 1)
                name = parts[0]
                if re.match(r"\d", parts[1]):
                    version = parts[1]

            detections.append(
                {
                    "name": name,
                    "category": "cms",
                    "version": version,
                    "confidence": 0.9,
                    "evidence": [f"meta generator: {gen}"],
                }
            )

        # Framework-specific DOM attributes
        dom_signatures = {
            r"data-reactroot": "React",
            r"id=\"__next\"": "Next.js",
            r"data-v-": "Vue.js",
            r"ng-version": "Angular",
            r"class=\"svelte-": "Svelte",
            r"data-nuxt": "Nuxt.js",
        }

        for pattern, name in dom_signatures.items():
            if re.search(pattern, html, re.IGNORECASE):
                detections.append(
                    {
                        "name": name,
                        "category": "framework",
                        "version": None,
                        "confidence": 0.8,
                        "evidence": [f"DOM pattern: {pattern}"],
                    }
                )

        return detections

    async def _analyze_via_js(self, ctx: ScanContext) -> list[dict[str, Any]]:
        detections: list[dict[str, Any]] = []

        try:
            from jaguar.browser.manager import BrowserManager
            from jaguar.browser.scripts import TECH_DETECT_SCRIPT

            browser = BrowserManager(headless=ctx.config.get("browser", {}).get("headless", True))
            page = await browser.new_page()

            try:
                await browser.navigate_and_wait(page, ctx.url)

                # Run the detection script
                results = await browser.inject_script(page, TECH_DETECT_SCRIPT)

                # Convert script results to standard format
                category_map = {
                    "react": "library",
                    "nextjs": "framework",
                    "vue": "framework",
                    "nuxt": "framework",
                    "angular": "framework",
                    "svelte": "framework",
                    "jquery": "library",
                    "wordpress": "cms",
                    "shopify": "ecommerce",
                    "cloudflare": "cdn",
                    "google_analytics": "analytics",
                    "tailwind": "css",
                    "bootstrap": "css",
                }

                for tech, data in results.items():
                    if data.get("found"):
                        name_display = tech.title()
                        if tech == "nextjs":
                            name_display = "Next.js"
                        elif tech == "vue":
                            name_display = "Vue.js"
                        elif tech == "jquery":
                            name_display = "jQuery"
                        elif tech == "wordpress":
                            name_display = "WordPress"

                        detections.append(
                            {
                                "name": name_display,
                                "category": category_map.get(tech, "unknown"),
                                "version": data.get("version"),
                                "confidence": data.get("confidence", 1.0),
                                "evidence": ["JavaScript Global Detection"],
                            }
                        )

            finally:
                await page.close()

        except Exception as e:
            logger.debug("JS tech detection failed: %s", e)

        return detections
