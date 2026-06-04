"""
Clone validation engine for JAGUAR.

Validates:
- CSS, JS, Images, Fonts, SVG, Manifest, Media
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

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

    @property
    def overall_health(self) -> float:
        cats = [self.html, self.css, self.js, self.images, self.fonts, self.svg, self.manifest, self.media, self.links]
        non_empty = [c for c in cats if c.total > 0]
        if not non_empty:
            return 100.0
        # If HTML has 0 resolved but some total, it means index.html or main pages failed!
        if self.html.total > 0 and self.html.resolved == 0:
            return 0.0
        return round(sum((c.resolved / c.total) * 100 for c in non_empty) / len(non_empty), 1)

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

    def validate(self) -> CloneReport:
        report = CloneReport()

        report.html.total = 1
        index_path = self.clone_dir / "index.html"
        if index_path.exists():
            report.html.resolved = 1
        else:
            report.html.missing.append("index.html")

        api_endpoints = ["/api/", "/graphql", "/auth/", "/login"]
        frontend_only_detected = False

        for html_file in self.clone_dir.rglob("*.html"):
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

                # Check CSS
                for link in soup.find_all("link", rel="stylesheet"):
                    self._check_asset(html_file, link.get("href"), report.css)

                # Check JS
                for script in soup.find_all("script", src=True):
                    self._check_asset(html_file, script.get("src"), report.js)

                # Check Images
                for img in soup.find_all("img", src=True):
                    src = img.get("src")
                    if src and src.endswith(".svg"):
                        self._check_asset(html_file, src, report.svg)
                    else:
                        self._check_asset(html_file, src, report.images)

                # Check Manifest
                for link in soup.find_all("link", rel="manifest"):
                    self._check_asset(html_file, link.get("href"), report.manifest)

                # Check Media
                for tag in soup.find_all(["video", "audio", "source"]):
                    self._check_asset(html_file, tag.get("src"), report.media)

            except Exception as e:
                logger.error("Validation error in %s: %s", html_file, e)

        if frontend_only_detected:
            logger.warning("\n[!] Frontend-only clone detected. Dynamic functionality depends on backend services and may not work offline.\n")

        # Check fonts referenced in CSS files
        for css_file in self.clone_dir.rglob("*.css"):
            try:
                content = css_file.read_text(encoding="utf-8", errors="replace")
                font_urls = re.findall(r"@font-face[^}]*?url\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", content)
                for font_url in font_urls:
                    self._check_asset(css_file, font_url, report.fonts)
            except Exception:
                pass

        logger.info("Clone health: %.1f%%", report.overall_health)
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
