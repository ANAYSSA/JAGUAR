"""
Async Website Cloner Engine for JAGUAR.

Downloads a website for offline viewing or deep analysis.
Supports standard static sites and modern JS/SPA frameworks via Playwright.

Requirement #8: Support static, React, Next.js, Vue, and SPAs.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import aiofiles
import aiohttp
from bs4 import BeautifulSoup

from jaguar.cloner.link_rewriter import LinkRewriter
from jaguar.cloner.spa_renderer import SPARenderer
from jaguar.core.http_client import HttpClient, HttpClientConfig
from jaguar.utils.url import extract_hostname, is_same_origin, normalize_url

logger = logging.getLogger("jaguar.cloner.engine")


class ClonerEngine:
    """Core website cloning engine."""

    def __init__(
        self,
        *,
        max_depth: int = 1,
        max_pages: int = 50,
        concurrency: int = 5,
        render_spa: bool = False,
        verify: bool = False,
        output_dir: str = "./jaguar-clones",
        config: dict[str, Any] | None = None,
        locale_override: str | None = None,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.concurrency = concurrency
        self.render_spa = render_spa
        self.verify = verify
        self.output_dir = output_dir
        self.config = config or {}
        self.clone_report: Any = None
        self.visual_result: Any = None

        self._visited: set[str] = set()
        self._queued: set[str] = set()
        self._queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self._assets_queue: asyncio.Queue[str] = asyncio.Queue()
        self._assets_visited: set[str] = set()

        self.http: HttpClient | None = None
        self.rewriter: LinkRewriter | None = None
        self.spa_renderer: SPARenderer | None = None
        self.browser_manager = None
        self.base_url = ""
        self.site_language = ""
        self.language_source = ""
        self.failed_assets_count = 0
        self.current_url = ""
        self.locale_override = locale_override
        self.system_language = "Unknown"
        self.final_site_language = "Unknown"

    def _determine_locale(self) -> None:
        """Determine the final locale to use based on strict priority."""
        # 1. Override via CLI
        if self.locale_override:
            self.site_language = self.locale_override
            self.selected_language = self.locale_override
            self.language_source = "CLI Override"
            self.system_language = self._get_windows_locale()
            return

        # 2. Configured User Language
        user_lang = self.config.get("cloner", {}).get("language")
        if user_lang:
            self.site_language = user_lang
            self.selected_language = user_lang
            self.language_source = "User Configured"
            self.system_language = self._get_windows_locale()
            return

        # 3. Windows OS Locale
        win_lang = self._get_windows_locale()
        self.site_language = win_lang
        self.selected_language = win_lang
        self.language_source = "OS Locale"
        self.system_language = win_lang

    def _get_windows_locale(self) -> str:
        try:
            import ctypes
            import locale
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            win_lang = locale.windows_locale.get(lang_id, "en_US")
            return win_lang.replace("_", "-")
        except Exception:
            return "en-US"

    def _get_accept_language_header(self) -> str:
        loc = self.site_language
        lang_code = loc.split("-")[0]
        if lang_code != loc:
            return f"{loc},{lang_code};q=0.9,en;q=0.8"
        return f"{loc},en;q=0.9"

    async def clone(self, url: str) -> str:
        """
        Start cloning process.
        Returns the absolute path to the directory containing the clone.
        """
        self.base_url = normalize_url(url)
        hostname = extract_hostname(self.base_url)

        # Setup output directory
        target_dir = Path(self.output_dir) / hostname
        target_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Starting clone of %s to %s (depth=%d, max_pages=%d, spa=%s)",
            self.base_url,
            target_dir,
            self.max_depth,
            self.max_pages,
            self.render_spa,
        )

        self.rewriter = LinkRewriter(self.base_url)

        # Setup browser for SPA rendering if requested
        if self.render_spa:
            try:
                from jaguar.browser.manager import BrowserManager

                self.browser_manager = BrowserManager(  # type: ignore
                    headless=self.config.get("browser", {}).get("headless", True)
                )
                await self.browser_manager.start()  # type: ignore
                self.spa_renderer = SPARenderer(self.browser_manager)
            except ImportError:
                logger.warning("Playwright not installed. SPA rendering disabled.")
                self.render_spa = False

        self._determine_locale()
        accept_lang = self._get_accept_language_header()

        http_config = HttpClientConfig(
            max_retries=2,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Accept-Language": accept_lang},
        )

        # Enqueue start URL
        self._queue.put_nowait((self.base_url, 0))
        self._queued.add(self.base_url)

        try:
            async with HttpClient(http_config) as http:
                self.http = http
                
                # Check root URL health and capture final site language
                try:
                    response = await self.http.get(self.base_url, use_cache=False)
                    self.final_site_language = response.headers.get("Content-Language", self.site_language).split(",")[0].strip()
                except Exception as e:
                    raise RuntimeError(f"Failed to fetch initial URL: {self.base_url}. Server may be down or nonexistent.") from e

                # Create workers for HTML pages
                page_workers = [
                    asyncio.create_task(self._page_worker(target_dir))
                    for _ in range(self.concurrency)
                ]

                # Create workers for assets
                asset_workers = [
                    asyncio.create_task(self._asset_worker(target_dir))
                    for _ in range(self.concurrency)
                ]

                # Wait for queues to empty with timeout protection
                try:
                    await asyncio.wait_for(self._queue.join(), timeout=30)
                    await asyncio.wait_for(self._assets_queue.join(), timeout=30)
                except TimeoutError:
                    logger.warning("Clone queues timed out during shutdown. Forcing exit.")

                # Cancel workers
                for w in page_workers + asset_workers:
                    w.cancel()

                # Await cancellation
                await asyncio.gather(*(page_workers + asset_workers), return_exceptions=True)

        finally:
            if self.browser_manager:
                await self.browser_manager.close()

        logger.info(
            "Cloning complete. Downloaded %d pages and %d assets.",
            len(self._visited),
            len(self._assets_visited),
        )

        # Post-clone phases
        await self._post_clone(target_dir)

        return str(target_dir.absolute())

    async def _post_clone(self, target_dir: Path) -> None:
        """Run CSS resolution, rebuild, validation, and optional visual compare."""
        from jaguar.cloner.css_resolver import CSSResolver
        from jaguar.cloner.rebuilder import Rebuilder
        from jaguar.cloner.validator import CloneValidator

        # Phase A: CSS dependency resolution
        logger.info("Phase: CSS dependency resolution")
        try:
            http_config = HttpClientConfig(
                max_retries=2,
                timeout=aiohttp.ClientTimeout(total=30),
            )
            async with HttpClient(http_config) as http:
                resolver = CSSResolver(http._session, self.base_url, target_dir)
                css_result = await resolver.resolve_all()
                logger.info(
                    "CSS resolved: %d deps, %d failed, %d fonts",
                    css_result.total_resolved,
                    css_result.total_failed,
                    len(css_result.fonts_downloaded),
                )
        except Exception as e:
            logger.warning("CSS resolution failed: %s", e)

        # Phase B: Rebuild (fix paths, entry point, manifests)
        logger.info("Phase: Rebuild")
        try:
            rebuilder = Rebuilder(target_dir, self.base_url)
            rebuild_summary = rebuilder.rebuild()
            logger.info("Rebuild summary: %s", rebuild_summary)
        except Exception as e:
            logger.warning("Rebuild failed: %s", e)

        # Phase C: Validate clone health
        logger.info("Phase: Validation")
        try:
            validator = CloneValidator(target_dir)
            self.clone_report = validator.validate()
            self.clone_report.system_language = self.system_language
            self.clone_report.selected_language = self.selected_language
            self.clone_report.final_site_language = self.final_site_language

            # Write CLONE_REPORT.md
            report_path = target_dir / "CLONE_REPORT.md"
            report_path.write_text(self.clone_report.to_markdown(), encoding="utf-8")
            logger.info("Clone health: %.1f%%", self.clone_report.overall_health)
        except Exception as e:
            logger.warning("Validation failed: %s", e)

        # Phase D: Visual comparison (if --verify)
        if self.verify:
            logger.info("Phase: Visual comparison")
            try:
                from jaguar.cloner.visual_compare import VisualCompare

                comparator = VisualCompare(target_dir)
                self.visual_result = await comparator.compare(self.base_url)
                logger.info("Visual accuracy: %.1f%%", self.visual_result.accuracy)

                failed = False
                if self.visual_result.accuracy < 98.0:
                    logger.error("Clone FAILED: Visual accuracy %.1f%% is below 98.0%% threshold.", self.visual_result.accuracy)
                    failed = True

                if self.visual_result.console_errors:
                    logger.error("Clone FAILED: Browser console contains resource failures (%d errors).", len(self.visual_result.console_errors))
                    for err in self.visual_result.console_errors:
                        logger.error("Browser Error: %s", err)
                    failed = True

                # Append visual report to CLONE_REPORT.md
                report_path = target_dir / "CLONE_REPORT.md"
                with report_path.open("a", encoding="utf-8") as f:
                    f.write("\n## Visual Verification\n")
                    f.write(self.visual_result.summary() + "\n")
                    if failed:
                        f.write("\n**STATUS: FAILED**\n")
                    else:
                        f.write("\n**STATUS: PASSED**\n")

            except Exception as e:
                logger.warning("Visual comparison failed: %s", e)

    async def _page_worker(self, base_dir: Path) -> None:
        """Worker that processes HTML pages."""
        while True:
            try:
                url, depth = await self._queue.get()
                self.current_url = url

                if len(self._visited) >= self.max_pages:
                    # Drain remaining queue instantly
                    while not self._queue.empty():
                        try:
                            self._queue.get_nowait()
                            self._queue.task_done()
                        except asyncio.QueueEmpty:
                            break
                    continue

                await self._process_page(url, depth, base_dir)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error processing page %s: %s", url, e)
            finally:
                self._queue.task_done()

    async def _asset_worker(self, base_dir: Path) -> None:
        """Worker that downloads static assets."""
        while True:
            try:
                url = await self._assets_queue.get()
                self.current_url = url
                await self._download_asset(url, base_dir)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error downloading asset %s: %s", url, e)
                self.failed_assets_count += 1
            finally:
                self._assets_queue.task_done()

    async def _process_page(self, url: str, depth: int, base_dir: Path) -> None:
        """Fetch, parse, rewrite, and save an HTML page."""
        self._visited.add(url)
        logger.debug("Processing page: %s (depth %d)", url, depth)

        assert self.http is not None
        assert self.rewriter is not None

        html_content = ""

        if self.render_spa and self.spa_renderer:
            # Render JS-heavy page
            try:
                html_content = await self.spa_renderer.render_to_static_html(url, locale=self.site_language)
            except Exception as e:
                logger.warning("SPA render failed for %s, falling back to basic HTTP: %s", url, e)

        if not html_content:
            # Basic HTTP fetch
            try:
                response = await self.http.get(url, use_cache=False)
                if not response.content_type.startswith("text/html"):
                    # Might be an asset wrongly queued as page
                    self._enqueue_asset(url)
                    return
                html_content = response.body
            except Exception as e:
                logger.error("Failed to fetch %s: %s", url, e)
                return

        # Parse HTML to find links and assets
        soup = BeautifulSoup(html_content, "lxml")

        # Queue assets (images, css, js)
        self._extract_and_queue_assets(soup, url)

        # Queue next pages if within depth limit
        if depth < self.max_depth:
            self._extract_and_queue_links(soup, url, depth + 1)

        # Rewrite links for local browsing
        rewritten_html = self.rewriter.rewrite_html(html_content, url)

        # Save to disk
        local_path = self._url_to_local_path(url, base_dir, is_html=True)
        await self._save_file(local_path, rewritten_html.encode("utf-8"))

    def _extract_and_queue_assets(self, soup: BeautifulSoup, current_url: str) -> None:
        """Find assets in HTML and add to download queue."""
        for tag, attr in [
            ("img", "src"),
            ("link", "href"),
            ("script", "src"),
            ("source", "src"),
            ("source", "srcset"),
        ]:
            for el in soup.find_all(tag, **{attr: True}):
                val = el[attr]
                # srcset can have multiple URLs
                urls = [u.split()[0] for u in val.split(",")] if attr == "srcset" else [val]

                for u in urls:
                    if u.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
                        continue

                    abs_url = urljoin(current_url, u)
                    if is_same_origin(self.base_url, abs_url):
                        self._enqueue_asset(abs_url)

    def _extract_and_queue_links(
        self, soup: BeautifulSoup, current_url: str, next_depth: int
    ) -> None:
        """Find internal HTML links and add to page queue."""
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue

            # Drop fragments
            href = href.split("#")[0]
            if not href:
                continue

            abs_url = urljoin(current_url, href)

            # Only queue same-origin pages
            if is_same_origin(self.base_url, abs_url) and abs_url not in self._queued:
                self._queued.add(abs_url)
                self._queue.put_nowait((abs_url, next_depth))

    def _enqueue_asset(self, url: str) -> None:
        """Add asset to download queue if not already seen."""
        if url not in self._assets_visited:
            self._assets_visited.add(url)
            self._assets_queue.put_nowait(url)

    async def _download_asset(self, url: str, base_dir: Path) -> None:
        """Download and save a static asset."""
        assert self.http is not None
        assert self.rewriter is not None

        try:
            # We use underlying aiohttp session for binary download
            async with self.http._session.get(url) as response:  # type: ignore
                if response.status != 200:
                    return

                content_type = response.headers.get("Content-Type", "")
                content = await response.read()

                # If it's CSS, rewrite url() paths
                if "text/css" in content_type:
                    try:
                        css_text = content.decode("utf-8")
                        rewritten_css = self.rewriter.rewrite_css(css_text, url)
                        content = rewritten_css.encode("utf-8")
                    except UnicodeDecodeError:
                        pass  # Keep binary if decoding fails

                local_path = self._url_to_local_path(url, base_dir, is_html=False)
                await self._save_file(local_path, content)

        except Exception as e:
            logger.debug("Failed to download asset %s: %s", url, e)

    def _url_to_local_path(self, url: str, base_dir: Path, is_html: bool) -> Path:
        """Convert a URL to an absolute filesystem path within base_dir."""
        parsed = urlparse(url)
        path = parsed.path

        if not path or path == "/":
            path = "/index.html"

        # Ensure HTML files have extension
        if is_html and not path.split("/")[-1].count("."):
            if not path.endswith("/"):
                path += "/index.html"
            else:
                path += "index.html"

        # Remove leading slash
        path = path.lstrip("/")

        # Avoid path traversal
        path = path.replace("../", "").replace("..\\", "")

        return base_dir / path

    async def _save_file(self, path: Path, data: bytes) -> None:
        """Save data to file, creating directories if needed."""
        path.parent.mkdir(parents=True, exist_ok=True)

        # Don't overwrite directories
        if path.is_dir():
            path = path / "index.html"

        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
