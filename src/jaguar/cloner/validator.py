"""
Clone validation engine for JAGUAR.

Validates:
- CSS, JS, Images, Fonts, SVG, Manifest, Media
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from playwright.async_api import ConsoleMessage, Error, Request, Response

logger = logging.getLogger("jaguar.cloner.validator")


@dataclass
class CategoryHealth:
    total: int = 0
    resolved: int = 0
    missing: list[str] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        if self.total == 0:
            return 100.0
        return round((self.resolved / self.total) * 100, 1)


@dataclass
class CloneReport:
    css: CategoryHealth = field(default_factory=CategoryHealth)
    js: CategoryHealth = field(default_factory=CategoryHealth)
    images: CategoryHealth = field(default_factory=CategoryHealth)
    fonts: CategoryHealth = field(default_factory=CategoryHealth)
    svg: CategoryHealth = field(default_factory=CategoryHealth)
    manifest: CategoryHealth = field(default_factory=CategoryHealth)
    media: CategoryHealth = field(default_factory=CategoryHealth)
    html: CategoryHealth = field(default_factory=CategoryHealth)
    links: CategoryHealth = field(default_factory=CategoryHealth)

    entry_point: str | None = None
    is_spa: bool = False

    system_language: str = "Unknown"
    selected_language: str = "Unknown"
    final_site_language: str = "Unknown"
    visual_accuracy: float | None = None
    has_rendering_errors: bool = False
    rendering_error_logs: list[str] = field(default_factory=list)
    language_mismatch: bool = False

    @property
    def overall_health(self) -> float:
        if self.language_mismatch:
            return 0.0
        cats = [self.html, self.css, self.js, self.images, self.fonts, self.svg, self.manifest, self.media, self.links]
        non_empty = [c for c in cats if c.total > 0]
        if not non_empty:
            score = 100.0
        else:
            # If HTML has 0 resolved but some total, it means index.html or main pages failed!
            if self.html.total > 0 and self.html.resolved == 0:
                score = 0.0
            else:
                score = sum((c.resolved / c.total) * 100 for c in non_empty) / len(non_empty)

        # Penalize for missing files in categories
        total_missing = self.total_missing
        if total_missing > 0:
            score -= min(40.0, total_missing * 2.0)

        # Deduct 2.0 points per console/runtime error up to 50.0 points
        if self.rendering_error_logs:
            score -= min(50.0, len(self.rendering_error_logs) * 2.0)

        # Hard limits based on categories
        if self.css.total > 0 and self.css.missing:
            score = min(score, 80.0)

        if self.js.total > 0 and self.js.missing:
            score = min(score, 80.0)

        if self.has_rendering_errors or self.rendering_error_logs:
            score = min(score, 90.0)

        if self.visual_accuracy is not None:
            if self.visual_accuracy < 80.0:
                score = min(score, 50.0)
            elif self.visual_accuracy < 90.0:
                score = min(score, 70.0)

        # Ensure we never return exactly 100% if any issues exist
        if score >= 100.0 and (total_missing > 0 or self.has_rendering_errors or self.rendering_error_logs or (self.visual_accuracy is not None and self.visual_accuracy < 100.0)):
            score = 99.0

        return max(0.0, round(score, 1))

    @property
    def total_missing(self) -> int:
        return sum(
            len(c.missing)
            for c in [self.html, self.css, self.js, self.images, self.fonts, self.svg, self.manifest, self.media, self.links]
        )

    def to_markdown(self) -> str:
        lines = [
            "# Clone Report",
            "",
            f"**Overall Health:** {self.overall_health}%",
            f"**Detected System Language:** {self.system_language}",
            f"**Selected Clone Language:** {self.selected_language}",
            f"**Final Site Language:** {self.final_site_language}",
            f"**Rendering Errors:** {'Yes' if self.has_rendering_errors else 'No'}",
            f"**Visual Accuracy:** {f'{self.visual_accuracy}%' if self.visual_accuracy else 'N/A'}",
            "",
        ]

        for name, cat in [
            ("HTML", self.html),
            ("CSS", self.css),
            ("JS", self.js),
            ("Images", self.images),
            ("Fonts", self.fonts),
            ("SVG", self.svg),
            ("Manifest", self.manifest),
            ("Media", self.media),
            ("Links", self.links),
        ]:
            if cat.total > 0 or name in ["HTML", "CSS", "JS", "Images", "Fonts"]:
                lines.append(f"{name}:")
                if cat.total == 0:
                    lines.append("0/0 OK")
                elif cat.total == cat.resolved:
                    lines.append(f"{cat.total}/{cat.total} OK")
                else:
                    lines.append(f"{cat.resolved}/{cat.total} OK")
                lines.append("")

        lines.append("Missing Assets / Broken Links / 404s:")
        lines.append(str(self.total_missing))
        lines.append("")

        all_missing = []
        for name, cat in [
            ("HTML", self.html),
            ("CSS", self.css),
            ("JS", self.js),
            ("Images", self.images),
            ("Fonts", self.fonts),
            ("SVG", self.svg),
            ("Manifest", self.manifest),
            ("Media", self.media),
            ("Links", self.links),
        ]:
            for m in cat.missing:
                all_missing.append(f"- [{name}] {m}")

        if all_missing:
            lines.append("\n## Missing Files")
            lines.extend(all_missing[:50])
            if len(all_missing) > 50:
                lines.append(f"... and {len(all_missing) - 50} more.")

        return "\n".join(lines)


class CloneValidator:
    def __init__(self, clone_dir: Path):
        self.clone_dir = clone_dir

    async def validate(self, base_url: str, browser_manager: Any = None) -> CloneReport:
        report = self._run_static_checks()

        # Check language_report.json
        try:
            import json as _json
            report_path = self.clone_dir / "language_report.json"
            if report_path.exists():
                lang_data = _json.loads(report_path.read_text(encoding="utf-8"))
                req_lang = lang_data.get("requested_language", "").lower()
                det_lang = lang_data.get("detected_html_lang")
                det_lang_str = str(det_lang).lower() if det_lang else ""

                if req_lang.startswith("en") and not det_lang_str.startswith("en"):
                    logger.error(f"[VALIDATION FAILED] Language mismatch: requested={req_lang} but html lang={det_lang}")
                    report.language_mismatch = True
                    report.has_rendering_errors = True
                    report.rendering_error_logs.append(f"[Language Mismatch] Requested {req_lang} but got {det_lang}")
        except Exception as e:
            logger.warning("Failed to check language validation: %s", e)

        report = await self._run_playwright_validation(report, base_url, browser_manager)

        logger.info("Clone health: %.1f%%", report.overall_health)
        return report

    def _run_static_checks(self, timeout: float = 0) -> CloneReport:
        import time
        start_time = time.time()

        report = CloneReport()

        from jaguar.cloner.server import detect_entry_point

        report.html.total = 1
        entry = detect_entry_point(str(self.clone_dir))
        entry_path = None

        if entry:
            report.html.resolved = 1
            entry_path = self.clone_dir / entry
        else:
            report.html.missing.append("index.html (or any valid entry point)")

        api_endpoints = ["/api/", "/graphql", "/auth/", "/login"]
        frontend_only_detected = False

        # Scan both .html AND .php files (Moodle uses .php pages with HTML content)
        # Filter to actual files only — Moodle stores data in dirs named like 'styles.php/'
        html_files = set(p for p in self.clone_dir.rglob("*.html") if p.is_file())
        html_files.update(p for p in self.clone_dir.rglob("*.php") if p.is_file())
        if entry_path and entry_path.exists() and entry_path.is_file():
            html_files.add(entry_path)

        for html_file in html_files:
            current_stage = "HTML/Routes"
            if timeout > 0 and (time.time() - start_time) > timeout:
                logger.warning("Validation timed out at stage '%s' after %.1fs, continuing...", current_stage, timeout)
                break
            try:
                content = html_file.read_text(encoding="utf-8", errors="replace")
                soup = BeautifulSoup(content, "lxml")

                # Check internal links and frontend-only triggers
                for a in soup.find_all("a", href=True):
                    href = a.get("href")
                    if any(ep in href for ep in api_endpoints):
                        frontend_only_detected = True
                    if href.startswith(("http", "mailto:", "tel:", "javascript:", "#")):
                        continue
                    self._check_asset(html_file, href, report.links)

                current_stage = "CSS"
                if timeout > 0 and (time.time() - start_time) > timeout:
                    logger.warning("Validation timed out at stage '%s' after %.1fs, continuing...", current_stage, timeout)
                    break
                for link in soup.find_all("link", rel="stylesheet"):
                    self._check_asset(html_file, link.get("href"), report.css)

                current_stage = "JS"
                if timeout > 0 and (time.time() - start_time) > timeout:
                    logger.warning("Validation timed out at stage '%s' after %.1fs, continuing...", current_stage, timeout)
                    break
                for script in soup.find_all("script", src=True):
                    self._check_asset(html_file, script.get("src"), report.js)

                current_stage = "Assets"
                if timeout > 0 and (time.time() - start_time) > timeout:
                    logger.warning("Validation timed out at stage '%s' after %.1fs, continuing...", current_stage, timeout)
                    break
                for img in soup.find_all("img", src=True):
                    src = img.get("src")
                    if src and src.endswith(".svg"):
                        self._check_asset(html_file, src, report.svg)
                    else:
                        self._check_asset(html_file, src, report.images)

                for link in soup.find_all("link", rel="manifest"):
                    self._check_asset(html_file, link.get("href"), report.manifest)

                for tag in soup.find_all(["video", "audio", "source"]):
                    self._check_asset(html_file, tag.get("src"), report.media)

            except Exception as e:
                logger.error("Validation error in %s: %s", html_file, e)

        if frontend_only_detected:
            logger.warning("\n[!] Frontend-only clone detected. Dynamic functionality depends on backend services and may not work offline.\n")

        # Check fonts referenced in CSS files
        current_stage = "Fonts/CSS Processing"
        for css_file in self.clone_dir.rglob("*.css"):
            if timeout > 0 and (time.time() - start_time) > timeout:
                logger.warning("Validation timed out at stage '%s' after %.1fs, continuing...", current_stage, timeout)
                break
            try:
                content = css_file.read_text(encoding="utf-8", errors="replace")
                font_urls = re.findall(r"@font-face[^}]*?url\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", content)
                for font_url in font_urls:
                    self._check_asset(css_file, font_url, report.fonts)
            except Exception:
                pass

        return report

    async def _run_playwright_validation(self, report: CloneReport, base_url: str, browser_manager: Any = None) -> CloneReport:
        """Run a full local render via Playwright to ensure the clone visually functions."""
        try:
            from jaguar.browser.manager import BrowserManager
            from jaguar.cloner.server import CloneServer
        except ImportError:
            return report

        browser = browser_manager
        should_close_browser = False
        server = None
        try:
            if not browser:
                browser = BrowserManager(headless=True)
                await browser.start()
                should_close_browser = True

            import socket
            sock = socket.socket()
            sock.bind(('', 0))
            port = sock.getsockname()[1]
            sock.close()

            server = CloneServer(str(self.clone_dir), port=port)
            local_url = server.start()

            logger.info("[DEBUG VALIDATOR] Calling new_page()")
            page = await browser.new_page()
            logger.info("[DEBUG VALIDATOR] new_page() returned")

            def handle_console(msg: ConsoleMessage) -> None:
                msg_lower = msg.text.lower()
                if msg.type == "error" or (msg.type == "warning" and ("failed" in msg_lower or "cors" in msg_lower or "mime" in msg_lower or "decode" in msg_lower)):
                    report.has_rendering_errors = True
                    report.rendering_error_logs.append(f"[Console] {msg.text}")

            def handle_pageerror(err: Error) -> None:
                report.has_rendering_errors = True
                report.rendering_error_logs.append(f"[JS Exception] {err.message}")

            def handle_requestfailed(req: Request) -> None:
                # 404s to local assets count as rendering errors
                if req.failure:
                    report.has_rendering_errors = True
                    report.rendering_error_logs.append(f"[Network] Failed {req.url}: {req.failure}")

            def handle_response(res: Response) -> None:
                if res.status >= 400:
                    report.has_rendering_errors = True
                    report.rendering_error_logs.append(f"[HTTP {res.status}] {res.url}")

            page.on("console", handle_console)
            page.on("pageerror", handle_pageerror)
            page.on("requestfailed", handle_requestfailed)
            page.on("response", handle_response)

            logger.info("[DEBUG VALIDATOR] Calling navigate_and_wait() to %s", local_url)
            await browser.navigate_and_wait(page, local_url)
            logger.info("[DEBUG VALIDATOR] navigate_and_wait() returned")

            logger.info("[DEBUG VALIDATOR] Sleeping 2s")
            await asyncio.sleep(2)  # Allow assets to load
            logger.info("[DEBUG VALIDATOR] Sleep returned")

            logger.info("[DEBUG VALIDATOR] Calling page.close()")
            await page.close()
            logger.info("[DEBUG VALIDATOR] page.close() returned")

        except Exception as e:
            logger.error("Playwright validation failed: %s", e)
        finally:
            if server:
                server.stop()
            if browser and should_close_browser:
                logger.info("[DEBUG VALIDATOR] Closing browser")
                await browser.close()
                logger.info("[DEBUG VALIDATOR] Browser closed")

        # Run visual pixel diffing
        try:
            from jaguar.cloner.visual_compare import VisualCompare
            vc = VisualCompare(self.clone_dir)
            vc_result = await vc.compare(original_url=base_url, browser_manager=browser)
            report.visual_accuracy = vc_result.accuracy
            if vc_result.console_errors:
                report.has_rendering_errors = True
        except Exception as e:
            logger.error("Visual compare failed: %s", e)

        return report

    def _check_asset(self, source_file: Path, asset_url: str | None, category: CategoryHealth) -> None:
        if not asset_url:
            return

        asset_url = asset_url.split("?")[0].split("#")[0]
        if asset_url.startswith(("data:", "http://", "https://", "javascript:")):
            return

        category.total += 1

        # Try resolving relative to the source file
        try:
            asset_path = (source_file.parent / asset_url).resolve()
            if asset_path.exists() and asset_path.is_file():
                category.resolved += 1
                return
        except Exception:
            pass

        # Try resolving relative to clone root
        try:
            asset_path = (self.clone_dir / asset_url.lstrip("/")).resolve()
            if asset_path.exists() and asset_path.is_file():
                category.resolved += 1
                return
        except Exception:
            pass

        category.missing.append(asset_url)
