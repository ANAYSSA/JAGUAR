"""
Async orchestration engine for JAGUAR.

The engine is the central coordinator that:
1. Accepts a URL and a list of analyzer names to run
2. Creates shared HTTP client and optionally launches Playwright
3. Performs initial retrieval (page fetch + resource discovery)
4. Dispatches analyzers concurrently via asyncio.gather
5. Runs lifecycle hooks (pre_scan, post_analyzer, post_scan)
6. Collects results, computes overall score
7. Generates recommendations and executive summary
8. Stores results for historical tracking
9. Passes results to selected reporter(s)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

from jaguar.core.http_client import HttpClient, HttpClientConfig
from jaguar.core.models import (
    AnalyzerCategory,
    AnalyzerResult,
    ScanContext,
    ScanResult,
    TechDetection,
)
from jaguar.core.plugin import AnalyzerProtocol, registry
from jaguar.core.recommendations import (
    generate_executive_summary,
    generate_recommendations,
)
from jaguar.core.scorer import compute_overall_score
from jaguar.utils.url import extract_base_url, extract_hostname, normalize_url

logger = logging.getLogger("jaguar.engine")


# Analyzer groups mapped to CLI commands
ANALYZER_GROUPS: dict[str, list[str]] = {
    "scan": ["security", "seo", "techstack"],
    "security": ["security", "secrets", "vulnerability"],
    "seo": ["seo"],
    "performance": ["performance"],
    "ux": ["ux"],
    "ai-detect": ["ai_detect"],
    "full": [
        "security",
        "secrets",
        "seo",
        "performance",
        "accessibility",
        "techstack",
        "ux",
        "ai_design",
        "ai_detect",
        "vulnerability",
    ],
}


class ScanEngine:
    """
    The main JAGUAR scan engine.

    Usage:
        engine = ScanEngine()
        result = await engine.scan("https://example.com", analyzers=["security", "seo"])
    """

    def __init__(
        self,
        *,
        http_config: HttpClientConfig | None = None,
        use_browser: bool = True,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._http_config = http_config or HttpClientConfig()
        self._use_browser = use_browser
        self._config = config or {}
        self._http: HttpClient | None = None
        self._browser_manager: Any = None  # Lazy import to avoid hard dep

    async def scan(
        self,
        url: str,
        *,
        analyzers: list[str] | None = None,
        group: str | None = None,
    ) -> ScanResult:
        """
        Execute a full scan of the given URL.

        Args:
            url: The URL to scan
            analyzers: Specific analyzer names to run (overrides group)
            group: Analyzer group name (e.g., 'full', 'security', 'scan')
        """
        start_time = time.monotonic()
        normalized = normalize_url(url)
        hostname = extract_hostname(normalized)
        base_url = extract_base_url(normalized)

        logger.info("Starting JAGUAR scan of %s", normalized)

        # Initialize result
        result = ScanResult(
            url=normalized,
            hostname=hostname,
        )

        try:
            # Determine which analyzers to run
            analyzer_names = self._resolve_analyzers(analyzers, group)
            logger.info("Running analyzers: %s", ", ".join(analyzer_names))

            # Initialize HTTP client
            async with HttpClient(self._http_config) as http:
                self._http = http

                # Phase 1: Initial retrieval
                context = await self._build_context(normalized, hostname, base_url, http)

                # Phase 2: Run lifecycle hooks (pre_scan)
                for hook in registry.hooks:
                    try:
                        context = await hook.pre_scan(context)
                    except Exception as e:
                        logger.warning("Hook %s pre_scan failed: %s", hook.name, e)

                # Phase 3: Optionally capture screenshots
                needs_browser = self._analyzers_need_browser(analyzer_names)
                if self._use_browser and needs_browser:
                    context = await self._setup_browser(context)

                # Phase 4: Dispatch analyzers concurrently
                analyzer_results = await self._run_analyzers(analyzer_names, context)

                # Phase 5: Collect results
                for ar in analyzer_results:
                    result.analyzer_results[ar.category.value] = ar

                    # Run post_analyzer hooks
                    for hook in registry.hooks:
                        try:
                            ar = await hook.post_analyzer(context, ar)
                        except Exception as e:
                            logger.warning("Hook %s post_analyzer failed: %s", hook.name, e)

                # Phase 6: Extract tech stack and AI detection
                if "techstack" in result.analyzer_results:
                    result.tech_stack = self._extract_tech_stack(
                        result.analyzer_results["techstack"]
                    )
                if "ai_detect" in result.analyzer_results:
                    result.ai_detection = self._extract_ai_detection(
                        result.analyzer_results["ai_detect"]
                    )

                # Phase 7: Screenshots
                result.screenshots = context.screenshots

                # Phase 8: Compute overall score
                category_scores: dict[AnalyzerCategory, int] = {}
                for name, ar in result.analyzer_results.items():
                    try:
                        cat = AnalyzerCategory(name)
                        category_scores[cat] = ar.score
                    except ValueError:
                        pass

                if category_scores:
                    result.overall_score = compute_overall_score(category_scores)

                # Phase 9: Generate recommendations
                result.recommendations = generate_recommendations(result)

                # Phase 10: Generate executive summary
                result.executive_summary = generate_executive_summary(result)

                # Phase 11: Run post_scan hooks
                for hook in registry.hooks:
                    try:
                        result = await hook.post_scan(result)
                    except Exception as e:
                        logger.warning("Hook %s post_scan failed: %s", hook.name, e)

        except ConnectionError as e:
            result.errors.append(f"Connection failed: {e}")
            logger.error("Scan failed: %s", e)
        except Exception as e:
            result.errors.append(f"Scan error: {e}")
            logger.exception("Unexpected scan error")
        finally:
            # Cleanup browser
            if self._browser_manager:
                with contextlib.suppress(Exception):
                    await self._browser_manager.close()

        # Finalize timing
        elapsed = (time.monotonic() - start_time) * 1000
        result.duration_ms = elapsed
        result.scan_completed_at = datetime.now(UTC)

        logger.info(
            "Scan complete: %s — Grade: %s (%s) in %.0fms",
            normalized,
            result.overall_score.grade.value if result.overall_score else "N/A",
            result.overall_score.score if result.overall_score else "N/A",
            elapsed,
        )

        return result

    async def _build_context(
        self,
        url: str,
        hostname: str,
        base_url: str,
        http: HttpClient,
    ) -> ScanContext:
        """Build the initial scan context by fetching the target URL."""
        logger.info("Fetching %s", url)

        response = await http.get(url)

        # Discover page resources from HTML
        resources = self._discover_resources(response.body, base_url)

        return ScanContext(
            url=url,
            hostname=hostname,
            base_url=base_url,
            response_status=response.status,
            response_headers=response.headers,
            response_body=response.body,
            final_url=response.final_url,
            redirect_chain=response.redirect_history,
            tls_info=response.tls_info,
            cookies=response.cookies,
            page_resources=resources,
            config=self._config,
        )

    def _discover_resources(self, html: str, base_url: str) -> list[dict[str, Any]]:
        """Extract resource references (JS, CSS, images, fonts) from HTML."""
        resources: list[dict[str, Any]] = []

        # Script tags
        for match in re.finditer(r'<script[^>]*\bsrc=["\']([^"\']+)["\']', html, re.IGNORECASE):
            resources.append({"type": "script", "url": match.group(1)})

        # Link tags (stylesheets, icons, etc.)
        for match in re.finditer(r'<link[^>]*\bhref=["\']([^"\']+)["\']', html, re.IGNORECASE):
            tag = match.group(0).lower()
            if "stylesheet" in tag:
                rtype = "stylesheet"
            elif "icon" in tag:
                rtype = "icon"
            elif "preload" in tag:
                rtype = "preload"
            else:
                rtype = "link"
            resources.append({"type": rtype, "url": match.group(1)})

        # Images
        for match in re.finditer(r'<img[^>]*\bsrc=["\']([^"\']+)["\']', html, re.IGNORECASE):
            resources.append({"type": "image", "url": match.group(1)})

        return resources

    def _resolve_analyzers(
        self,
        names: list[str] | None,
        group: str | None,
    ) -> list[str]:
        """Resolve analyzer names from explicit list or group."""
        if names:
            return names

        if group and group in ANALYZER_GROUPS:
            return ANALYZER_GROUPS[group]

        # Default to quick scan
        return ANALYZER_GROUPS["scan"]

    def _analyzers_need_browser(self, names: list[str]) -> bool:
        """Check if any requested analyzer needs a browser."""
        browser_analyzers = {
            "accessibility",
            "ux",
            "ai_design",
            "ai_detect",
        }
        return bool(set(names) & browser_analyzers)

    async def _setup_browser(self, context: ScanContext) -> ScanContext:
        """Initialize Playwright browser and capture screenshots."""
        try:
            from jaguar.browser.manager import BrowserManager

            self._browser_manager = BrowserManager()
            await self._browser_manager.start()
            context.browser_available = True

            # Capture screenshots (Requirement #5)
            from jaguar.browser.screenshots import capture_screenshot_gallery

            screenshots = await capture_screenshot_gallery(self._browser_manager, context.url)
            context.screenshots = screenshots

            logger.info("Browser initialized, %d screenshots captured", len(screenshots))

        except ImportError:
            logger.warning(
                "Playwright not installed. Browser-dependent analyzers will use fallback mode. "
                "Install with: pip install jaguar[browser]"
            )
        except Exception as e:
            logger.warning("Browser setup failed: %s. Continuing without browser.", e)

        return context

    async def _run_analyzers(
        self,
        names: list[str],
        context: ScanContext,
    ) -> list[AnalyzerResult]:
        """Run all requested analyzers concurrently."""
        tasks = []
        for name in names:
            analyzer = registry.get_analyzer(name)
            if analyzer:
                tasks.append(self._run_single_analyzer(analyzer, context))
            else:
                logger.warning("Analyzer '%s' not found in registry", name)

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)

        analyzer_results: list[AnalyzerResult] = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("Analyzer failed: %s", r)
            elif isinstance(r, AnalyzerResult):
                analyzer_results.append(r)

        return analyzer_results

    async def _run_single_analyzer(
        self,
        analyzer: AnalyzerProtocol,
        context: ScanContext,
    ) -> AnalyzerResult:
        """Run a single analyzer with timing."""
        start = time.monotonic()
        logger.info("Running analyzer: %s", analyzer.name)

        try:
            result = await analyzer.analyze(context)
            result.duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "Analyzer %s completed: score=%d, grade=%s (%.0fms)",
                analyzer.name,
                result.score,
                result.grade.value,
                result.duration_ms,
            )
            return result
        except Exception as e:
            logger.error("Analyzer %s failed: %s", analyzer.name, e, exc_info=True)
            raise

    @staticmethod
    def _extract_tech_stack(result: AnalyzerResult) -> list[TechDetection]:
        """Extract tech detections from techstack analyzer result."""
        detections = result.raw_data.get("detections", [])
        return [TechDetection(**d) for d in detections if isinstance(d, dict)]

    @staticmethod
    def _extract_ai_detection(result: AnalyzerResult) -> Any:
        """Extract AI detection data from ai_detect analyzer result."""
        from jaguar.core.models import AIDetectionResult

        data = result.raw_data.get("ai_detection")
        if isinstance(data, dict):
            return AIDetectionResult(**data)
        return None
