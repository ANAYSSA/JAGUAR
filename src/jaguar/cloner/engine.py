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
        self._worker_states: dict[str, str] = {}
        self._active_fetches: set[str] = set()

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
        self.browser_navigator_language: str | None = None
        self.browser_navigator_languages: list[str] | None = None
        self.all_cookies: list[str] = []
        self.all_redirects: list[str] = []

    def _determine_locale(self) -> None:
        """Determine the final locale to use based on strict priority."""
        win_lang = self._get_windows_locale()
        self.system_language = win_lang

        # 1. Override via CLI
        if self.locale_override and self.locale_override != "auto":
            self.site_language = self.locale_override
            self.selected_language = self.locale_override
            self.language_source = "CLI Override"
            return

        # 2. Configured User Language
        user_lang = self.config.get("cloner", {}).get("language")
        if user_lang and user_lang != "auto":
            self.site_language = user_lang
            self.selected_language = user_lang
            self.language_source = "User Configured"
            return

        # 3. Auto fallback to Windows OS Locale
        self.site_language = win_lang
        self.selected_language = win_lang
        self.language_source = "OS Locale (Auto)"

    def _get_windows_locale(self) -> str:
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
                return buf.value.replace("_", "-")
        except Exception:
            pass

        try:
            import ctypes
            import locale
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            win_lang = locale.windows_locale.get(lang_id, "en_US")
            return win_lang.replace("_", "-")
        except Exception:
            pass

        try:
            import locale
            loc = locale.getdefaultlocale()[0]
            if loc:
                return loc.replace("_", "-")
        except Exception:
            pass

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
                self.spa_renderer.clone_dir = target_dir
            except ImportError:
                logger.warning("Playwright not installed. SPA rendering disabled.")
                self.render_spa = False

        self._determine_locale()
        accept_lang = self._get_accept_language_header()

        lang_code = self.site_language.split("-")[0].strip()
        cookie_header = (
            f"locale={self.site_language}; "
            f"lang={lang_code}; "
            f"language={lang_code}; "
            f"NEXT_LOCALE={self.site_language}; "
            f"GH_LOCALE={self.site_language}"
        )
        http_config = HttpClientConfig(
            max_retries=2,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "Accept-Language": accept_lang,
                "Cookie": cookie_header,
            },
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

                # Wait for queues to empty, controlling progress and detecting stalls
                stalls = 0
                last_visited = 0
                last_assets = 0
                last_queue_size = -1
                last_active_tasks = 0

                try:
                    while True:
                        await asyncio.sleep(1)

                        current_visited = len(self._visited)
                        current_assets = len(self._assets_visited)
                        current_queue_size = self._queue.qsize() + self._assets_queue.qsize()
                        current_active_tasks = len(self._active_fetches)

                        active_workers = len([k for k, v in self._worker_states.items() if v != "waiting for task" and v != "cancelled"])
                        pending_tasks = len(self._active_fetches)

                        if (current_visited == last_visited and
                            current_assets == last_assets and
                            current_queue_size == last_queue_size and
                            current_active_tasks == last_active_tasks):
                            stalls += 1
                        else:
                            stalls = 0

                        last_visited = current_visited
                        last_assets = current_assets
                        last_queue_size = current_queue_size
                        last_active_tasks = current_active_tasks

                        # Check if done: queue empty, workers idle, pending tasks 0
                        if current_queue_size == 0 and active_workers == 0 and pending_tasks == 0:
                            logger.info("\nQueue empty")
                            logger.info("Workers idle")
                            logger.info("Pending tasks 0")
                            logger.info("Finalizing clone")
                            break

                        if stalls >= 15:
                            logger.error("\n\033[91m[DEADLOCK DETECTED] Clone stalled for 15s!\033[0m")
                            logger.error("Reason: Processed URLs, downloaded assets, queue size, and active task count remained unchanged for 15 consecutive seconds.")

                            logger.error("\n--- Active Asyncio Tasks ---")
                            try:
                                for t in asyncio.all_tasks():
                                    logger.error(f"  Task {t.get_name()}: coro={t.get_coro()}")
                            except Exception as e:
                                logger.error(f"  Failed to dump tasks: {e}")

                            logger.error(f"Current URL: {getattr(self, 'current_url', 'Unknown')}")

                            logger.error("\n--- Worker States ---")
                            for k, v in self._worker_states.items():
                                logger.error(f"  {k}: {v}")

                            logger.error("\n--- Queue Contents ---")
                            try:
                                page_items = list(getattr(self._queue, "_queue", []))
                                asset_items = list(getattr(self._assets_queue, "_queue", []))
                                logger.error(f"  Page Queue: {page_items}")
                                logger.error(f"  Asset Queue: {asset_items}")
                            except Exception as e:
                                logger.error(f"  Failed to dump queues: {e}")

                            logger.error("\n--- Awaiting Futures / Pending Tasks ---")
                            for req_url in self._active_fetches:
                                logger.error(f"  Awaiting/Pending Fetch: {req_url}")

                            raise RuntimeError("Clone stalled due to deadlock/inactivity.")
                finally:
                    # Cancel workers
                    for w in page_workers + asset_workers:
                        w.cancel()

                    # Await cancellation
                    await asyncio.gather(*(page_workers + asset_workers), return_exceptions=True)

            logger.info(
                "Cloning complete. Downloaded %d pages and %d assets.",
                len(self._visited),
                len(self._assets_visited),
            )

            # Save locale info for serving later
            try:
                locale_data = {
                    "locale": self.site_language,
                    "language": self.site_language.split("-")[0],
                    "accept_language": f"{self.site_language},{self.site_language.split('-')[0]};q=0.9,en;q=0.8"
                }
                import json
                (target_dir / ".jaguar-locale.json").write_text(json.dumps(locale_data), encoding="utf-8")
            except Exception as e:
                logger.warning("Failed to save locale info: %s", e)

            # Post-clone phases while browser is still active
            await self._post_clone(target_dir)

            # Verify local asset existence
            missing_assets = []
            static_extensions = {
                ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
                ".ico", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".json",
                ".mp4", ".mp3", ".ogg", ".webm", ".map", ".xml"
            }
            for url in self._assets_visited:
                parsed_url = urlparse(url)
                url_path = parsed_url.path.lower()
                has_static_ext = any(url_path.endswith(ext) for ext in static_extensions)
                if not has_static_ext:
                    continue  # Skip HTML, PHP, and other non-static assets
                local_path = self._url_to_local_path(url, target_dir, is_html=False)
                if not local_path.exists() or local_path.stat().st_size == 0:
                    missing_assets.append(url)

            if missing_assets:
                logger.error(f"\n\033[91m[CLONE INCOMPLETE] {len(missing_assets)} referenced assets are missing or empty!\033[0m")
                for u in missing_assets[:10]:
                    logger.error(f"  Missing: {u}")
                raise RuntimeError(f"Clone failed: {len(missing_assets)} referenced assets are missing.")

        finally:
            if self.browser_manager:
                await self.browser_manager.close()

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

        # Phase B.5: Write language report
        try:
            import json as _json

            from bs4 import BeautifulSoup

            from jaguar.cloner.server import detect_entry_point

            entry = detect_entry_point(str(target_dir))
            html_lang = None
            if entry:
                entry_file = target_dir / entry
                if entry_file.exists():
                    soup = BeautifulSoup(entry_file.read_text(encoding="utf-8", errors="replace"), "lxml")
                    html_tag = soup.find("html")
                    if html_tag and hasattr(html_tag, "get"):
                        html_lang = html_tag.get("lang")

            logger.info("=== LANGUAGE SOURCES DIAGNOSTIC DUMP ===")
            logger.info(f"  Accept-Language Header: {self._get_accept_language_header()}")
            logger.info(f"  Playwright Locale Option: {self.site_language}")
            logger.info(f"  navigator.language: {getattr(self, 'browser_navigator_language', None)}")
            logger.info(f"  navigator.languages: {getattr(self, 'browser_navigator_languages', None)}")
            logger.info(f"  cookies: {list(set(self.all_cookies))}")
            logger.info(f"  response redirects: {list(set(self.all_redirects))}")
            logger.info(f"  Detected HTML Lang Attribute on Disk: {html_lang}")
            logger.info("========================================")

            lang_report = {
                "requested_language": self.site_language,
                "final_language": self.final_site_language,
                "detected_html_lang": html_lang
            }
            (target_dir / "language_report.json").write_text(_json.dumps(lang_report, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to create language_report.json: %s", e)

        # Phase C: Validate clone health (Universal Rendering Validation)
        logger.info("Phase: Validation (Playwright-based)")
        try:
            validator = CloneValidator(target_dir)
            # Await Playwright rendering validation
            self.clone_report = await validator.validate(self.base_url, self.browser_manager)
            self.clone_report.system_language = self.system_language
            self.clone_report.selected_language = self.selected_language
            self.clone_report.final_site_language = self.final_site_language

            # Prevent 100% false positives
            if getattr(self.clone_report, "has_rendering_errors", False) and self.clone_report.overall_health == 100.0:
                self.clone_report.html.resolved -= 1  # Force sub-100% health if there are silent console errors/broken requests

            # Write CLONE_REPORT.md
            report_path = target_dir / "CLONE_REPORT.md"
            report_path.write_text(self.clone_report.to_markdown(), encoding="utf-8")
            logger.info("Clone health: %.1f%%", self.clone_report.overall_health)
        except Exception as e:
            logger.warning("Validation failed: %s", e)

    async def _monitor_deadlock(self, workers: list[asyncio.Task[Any]]) -> None:
        """Monitor queues and workers to detect infinite clone deadlocks."""
        pass

    async def _page_worker(self, base_dir: Path) -> None:
        """Worker that processes HTML pages."""
        task_id = f"page_worker_{id(asyncio.current_task())}"
        while True:
            try:
                self._worker_states[task_id] = "waiting for task"
                url, depth = await self._queue.get()
                self.current_url = url
                self._worker_states[task_id] = f"processing {url}"

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
                self._worker_states[task_id] = "cancelled"
                break
            except Exception as e:
                logger.error("Error processing page %s: %s", url, e)
            finally:
                self._queue.task_done()

    async def _asset_worker(self, base_dir: Path) -> None:
        """Worker that downloads static assets."""
        task_id = f"asset_worker_{id(asyncio.current_task())}"
        while True:
            try:
                self._worker_states[task_id] = "waiting for task"
                url = await self._assets_queue.get()
                self.current_url = url
                self._worker_states[task_id] = f"downloading {url}"
                await self._download_asset(url, base_dir)
            except asyncio.CancelledError:
                self._worker_states[task_id] = "cancelled"
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
        response_obj = None

        if self.render_spa and self.spa_renderer:
            # Render JS-heavy page
            try:
                self._active_fetches.add(url)
                html_content = await asyncio.wait_for(
                    self.spa_renderer.render_to_static_html(url, locale=self.site_language),
                    timeout=20.0
                )
                browser_nav_lang = getattr(self.spa_renderer, "browser_navigator_language", None)
                if browser_nav_lang is not None:
                    self.browser_navigator_language = str(browser_nav_lang)
                browser_nav_langs = getattr(self.spa_renderer, "browser_navigator_languages", None)
                if browser_nav_langs is not None:
                    self.browser_navigator_languages = browser_nav_langs
                browser_cookies = getattr(self.spa_renderer, "browser_cookies", None)
                if browser_cookies is not None:
                    self.all_cookies.append(str(browser_cookies))
                browser_redirects = getattr(self.spa_renderer, "browser_redirects", None)
                if browser_redirects is not None:
                    self.all_redirects.extend(browser_redirects)
            except Exception as e:
                logger.warning("SPA render failed for %s, falling back to basic HTTP: %s", url, e)
            finally:
                self._active_fetches.discard(url)

        if not html_content:
            # Basic HTTP fetch
            try:
                self._active_fetches.add(url)
                response_obj = await self.http.get(url, use_cache=False)
                if not response_obj.content_type.startswith("text/html"):
                    # Might be an asset wrongly queued as page
                    self._enqueue_asset(url)
                    return
                html_content = response_obj.body
                if response_obj.cookies:
                    self.all_cookies.extend(f"{c['name']}={c['value']}" for c in response_obj.cookies)
                if response_obj.redirect_history:
                    self.all_redirects.extend(response_obj.redirect_history)
            except Exception as e:
                logger.error("Failed to fetch %s: %s", url, e)
                return
            finally:
                self._active_fetches.discard(url)

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

        # Save metadata for the page
        content_type = "text/html"
        content_encoding = ""
        cache_control = ""
        if response_obj:
            content_type = response_obj.headers.get("Content-Type", "text/html")
            content_encoding = response_obj.headers.get("Content-Encoding", "")
            if content_encoding.lower() in ("gzip", "deflate", "br", "zstd"):
                content_encoding = ""
            cache_control = response_obj.headers.get("Cache-Control", "")

        meta = {
            "Content-Type": content_type,
            "Content-Encoding": content_encoding,
            "Cache-Control": cache_control
        }
        import json
        meta_path = local_path.with_name(local_path.name + ".meta.json")
        await self._save_file(meta_path, json.dumps(meta).encode("utf-8"))

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
                if tag == "link":
                    rel = el.get("rel", [])
                    if isinstance(rel, str):
                        rel = [rel]
                    rel_lower = [r.lower() for r in rel]
                    skip_rels = {"canonical", "alternate", "prev", "next", "search", "help", "license", "author", "pingback"}
                    if any(r in skip_rels for r in rel_lower):
                        continue

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
            self._active_fetches.add(url)
            async with asyncio.timeout(20.0):
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

                # Capture redirects/cookies
                if self.http and self.http._session:
                    for cookie in self.http._session.cookie_jar:
                        self.all_cookies.append(f"{cookie.key}={cookie.value}")
                if response.history:
                    self.all_redirects.extend(str(h.url) for h in response.history)

                local_path = self._url_to_local_path(url, base_dir, is_html=False)
                await self._save_file(local_path, content)

                # Save metadata for LMS / Server
                content_encoding = response.headers.get("Content-Encoding", "")
                if content_encoding.lower() in ("gzip", "deflate", "br", "zstd"):
                    content_encoding = ""

                meta = {
                    "Content-Type": content_type,
                    "Content-Encoding": content_encoding,
                    "Cache-Control": response.headers.get("Cache-Control", "")
                }
                import json
                meta_path = local_path.with_name(local_path.name + ".meta.json")
                await self._save_file(meta_path, json.dumps(meta).encode("utf-8"))

        except Exception as e:
            logger.debug("Failed to download asset %s: %s", url, e)
        finally:
            self._active_fetches.discard(url)

    def _url_to_local_path(self, url: str, base_dir: Path, is_html: bool) -> Path:
        """Convert a URL to an absolute filesystem path within base_dir."""
        from urllib.parse import unquote
        parsed = urlparse(url)
        path = unquote(parsed.path)

        if not path or path == "/":
            path = "/index.html"

        # If there are query parameters, append hash to distinguish assets
        if parsed.query:
            import hashlib
            import posixpath
            query_hash = hashlib.sha256(parsed.query.encode("utf-8")).hexdigest()[:8]
            base, ext = posixpath.splitext(path)
            if ext:
                path = f"{base}_{query_hash}{ext}"
            else:
                path = f"{path}_{query_hash}"

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

    def _resolve_file_dir_conflict(self, path: Path) -> None:
        """
        Ensure no parent directory of path is actually a file on disk.
        If a parent directory is a file, convert it to a directory
        and move its contents to that directory's index.html.
        """
        for parent in list(path.parents)[::-1]:
            if parent.exists() and parent.is_file():
                logger.info("Converting conflicting file %s to directory to allow subpaths", parent)
                try:
                    content = parent.read_bytes()
                    meta_path = parent.with_name(parent.name + ".meta.json")
                    meta_content = None
                    if meta_path.exists() and meta_path.is_file():
                        meta_content = meta_path.read_bytes()

                    parent.unlink()
                    if meta_path.exists() and meta_path.is_file():
                        meta_path.unlink()

                    parent.mkdir(parents=True, exist_ok=True)
                    index_path = parent / "index.html"
                    index_path.write_bytes(content)
                    if meta_content is not None:
                        new_meta_path = index_path.with_name(index_path.name + ".meta.json")
                        new_meta_path.write_bytes(meta_content)
                except Exception as e:
                    logger.debug("Failed to resolve conflict at %s: %s", parent, e)

    async def _save_file(self, path: Path, data: bytes) -> None:
        """Save data to file, creating directories if needed."""
        self._resolve_file_dir_conflict(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Don't overwrite directories
        if path.is_dir():
            path = path / "index.html"

        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
