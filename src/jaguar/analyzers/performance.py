"""
Performance analyzer for JAGUAR.

Measures page/resource sizes, compression, caching, and optionally
integrates with Lighthouse CLI for Core Web Vitals.
Lighthouse is optional with graceful fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil

from jaguar.analyzers.base import BaseAnalyzer
from jaguar.core.models import AnalyzerCategory, Finding, ScanContext, Severity

logger = logging.getLogger("jaguar.analyzers.performance")


class PerformanceAnalyzer(BaseAnalyzer):
    """Website performance analyzer."""

    name = "performance"
    category = AnalyzerCategory.PERFORMANCE
    weight = 1.2

    async def _run_checks(self, context: ScanContext) -> list[Finding]:
        findings: list[Finding] = []

        findings.append(self._check_page_size(context))
        findings.extend(self._check_resource_sizes(context))
        findings.append(self._check_compression(context))
        findings.append(self._check_cache_headers(context))
        findings.append(self._check_response_time(context))
        findings.append(self._check_resource_count(context))

        # Optional Lighthouse integration
        lighthouse_findings = await self._run_lighthouse(context)
        if lighthouse_findings:
            findings.extend(lighthouse_findings)

        return findings

    def _check_page_size(self, ctx: ScanContext) -> Finding:
        """Check total HTML page size."""
        size_bytes = len(ctx.response_body.encode("utf-8"))
        size_kb = size_bytes / 1024
        size_mb = size_kb / 1024

        if size_kb > 3000:
            return Finding(
                name="large-page-size",
                title="Page Size Excessive",
                description=f"HTML document is {size_mb:.1f} MB ({size_kb:.0f} KB). Very large pages hurt load time.",
                passed=False,
                severity=Severity.HIGH,
                score_modifier=-15,
                data={"size_bytes": size_bytes, "size_kb": round(size_kb)},
                recommendation="Reduce HTML size by removing inline assets, unused code, and optimizing content delivery.",
            )
        if size_kb > 1000:
            return Finding(
                name="moderate-page-size",
                title="Page Size Large",
                description=f"HTML document is {size_kb:.0f} KB.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-5,
                data={"size_bytes": size_bytes, "size_kb": round(size_kb)},
                recommendation="Consider optimizing HTML size for faster initial load.",
            )
        return Finding(
            name="page-size-ok",
            title="Page Size Acceptable",
            description=f"HTML document is {size_kb:.0f} KB.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={"size_bytes": size_bytes, "size_kb": round(size_kb)},
        )

    def _check_resource_sizes(self, ctx: ScanContext) -> list[Finding]:
        """Analyze resource types and counts."""
        findings: list[Finding] = []
        resources = ctx.page_resources

        js_count = sum(1 for r in resources if r.get("type") == "script")
        css_count = sum(1 for r in resources if r.get("type") == "stylesheet")
        sum(1 for r in resources if r.get("type") == "image")

        if js_count > 20:
            findings.append(
                Finding(
                    name="excessive-js-files",
                    title="Too Many JavaScript Files",
                    description=f"Page loads {js_count} JavaScript files. Consider bundling.",
                    passed=False,
                    severity=Severity.MEDIUM,
                    score_modifier=-10,
                    data={"count": js_count},
                    recommendation="Bundle JavaScript files to reduce HTTP requests.",
                )
            )

        if css_count > 10:
            findings.append(
                Finding(
                    name="excessive-css-files",
                    title="Too Many CSS Files",
                    description=f"Page loads {css_count} CSS files.",
                    passed=False,
                    severity=Severity.LOW,
                    score_modifier=-5,
                    data={"count": css_count},
                    recommendation="Bundle CSS files to reduce HTTP requests.",
                )
            )

        return findings

    def _check_compression(self, ctx: ScanContext) -> Finding:
        """Check if response is compressed."""
        encoding = ctx.response_headers.get("Content-Encoding", "").lower()

        if encoding in ("gzip", "br", "zstd", "deflate"):
            return Finding(
                name="compression-enabled",
                title="Compression Enabled",
                description=f"Response uses {encoding} compression.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=5,
                data={"encoding": encoding},
            )
        return Finding(
            name="no-compression",
            title="No Compression",
            description="Response is not compressed. Enable gzip or Brotli for 60-80% size reduction.",
            passed=False,
            severity=Severity.HIGH,
            score_modifier=-15,
            recommendation="Enable gzip or Brotli compression on your server for text resources.",
        )

    def _check_cache_headers(self, ctx: ScanContext) -> Finding:
        """Check caching headers."""
        cache_control = ctx.response_headers.get("Cache-Control", "")
        etag = ctx.response_headers.get("ETag", "")
        last_modified = ctx.response_headers.get("Last-Modified", "")

        has_cache = bool(cache_control) or bool(etag) or bool(last_modified)

        if not has_cache:
            return Finding(
                name="no-cache-headers",
                title="No Cache Headers",
                description="No Cache-Control, ETag, or Last-Modified headers found.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-10,
                recommendation="Configure Cache-Control headers for static assets.",
            )

        if "no-store" in cache_control or "no-cache" in cache_control:
            return Finding(
                name="cache-disabled",
                title="Caching Disabled",
                description=f"Cache-Control: {cache_control}. Consider enabling caching for better performance.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
                data={"cache_control": cache_control},
            )

        return Finding(
            name="cache-headers-present",
            title="Cache Headers Configured",
            description=f"Cache-Control: {cache_control}"
            if cache_control
            else "ETag/Last-Modified present.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={
                "cache_control": cache_control,
                "etag": bool(etag),
                "last_modified": bool(last_modified),
            },
        )

    def _check_response_time(self, ctx: ScanContext) -> Finding:
        """Check initial response time from headers/context."""
        # Use server timing if available
        server_timing = ctx.response_headers.get("Server-Timing", "")

        return Finding(
            name="response-time-info",
            title="Response Time",
            description=f"Server timing header: {server_timing}"
            if server_timing
            else "No Server-Timing header present.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={"server_timing": server_timing},
        )

    def _check_resource_count(self, ctx: ScanContext) -> Finding:
        """Check total number of resources."""
        count = len(ctx.page_resources)
        if count > 100:
            return Finding(
                name="excessive-resources",
                title="Excessive Resource Count",
                description=f"Page references {count} resources. High request count impacts load time.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-10,
                data={"count": count},
                recommendation="Reduce resource count through bundling, lazy loading, and removing unused assets.",
            )
        return Finding(
            name="resource-count-ok",
            title="Resource Count Acceptable",
            description=f"Page references {count} resources.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={"count": count},
        )

    async def _run_lighthouse(self, ctx: ScanContext) -> list[Finding]:
        """
        Optionally run Lighthouse CLI for Core Web Vitals.

        Returns empty list if Lighthouse is not installed.
        """
        lighthouse_path = shutil.which("lighthouse")
        if not lighthouse_path:
            logger.info("Lighthouse CLI not found — using built-in performance checks only.")
            return []

        try:
            cmd = [
                lighthouse_path,
                ctx.url,
                "--output=json",
                "--quiet",
                "--chrome-flags=--headless --no-sandbox",
                "--only-categories=performance",
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                logger.warning("Lighthouse exited with code %d", proc.returncode)
                return []

            data = json.loads(stdout.decode())
            return self._parse_lighthouse_results(data)

        except TimeoutError:
            logger.warning("Lighthouse timed out after 120 seconds.")
            return []
        except Exception as e:
            logger.warning("Lighthouse failed: %s", e)
            return []

    def _parse_lighthouse_results(self, data: dict) -> list[Finding]:  # type: ignore
        """Parse Lighthouse JSON output into findings."""
        findings: list[Finding] = []
        categories = data.get("categories", {})
        perf = categories.get("performance", {})
        score = perf.get("score")

        if score is not None:
            score_100 = int(score * 100)
            findings.append(
                Finding(
                    name="lighthouse-performance",
                    title="Lighthouse Performance Score",
                    description=f"Lighthouse performance score: {score_100}/100.",
                    passed=score_100 >= 50,
                    severity=Severity.INFO,
                    score_modifier=0,
                    data={"lighthouse_score": score_100},
                )
            )

        # Extract Core Web Vitals
        audits = data.get("audits", {})
        vitals = {
            "largest-contentful-paint": ("Largest Contentful Paint", 2500),
            "first-contentful-paint": ("First Contentful Paint", 1800),
            "total-blocking-time": ("Total Blocking Time", 200),
            "cumulative-layout-shift": ("Cumulative Layout Shift", 0.1),
            "speed-index": ("Speed Index", 3400),
        }

        for audit_id, (label, threshold) in vitals.items():
            audit = audits.get(audit_id, {})
            value = audit.get("numericValue")
            if value is not None:
                display = audit.get("displayValue", str(value))
                passed = value <= threshold
                findings.append(
                    Finding(
                        name=f"cwv-{audit_id}",
                        title=label,
                        description=f"{label}: {display}",
                        passed=passed,
                        severity=Severity.INFO,
                        score_modifier=0,
                        data={"value": value, "threshold": threshold, "display": display},
                    )
                )

        return findings
