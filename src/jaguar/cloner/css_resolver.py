"""
Recursive CSS dependency resolver for JAGUAR Cloner.

Parses CSS files to find and download:
- @import url(...) / @import "..."
- background: url(...)
- @font-face src: url(...)
- cursor: url(...)
- list-style-image: url(...)

Downloads each dependency, rewrites paths to local,
and recurses into imported CSS files up to a configurable depth.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("jaguar.cloner.css_resolver")

# Max recursion depth for @import chains
MAX_CSS_DEPTH = 5

# Regex patterns
IMPORT_PATTERN = re.compile(
    r"""@import\s+(?:url\(\s*['"]?([^'")]+)['"]?\s*\)|['"]([^'"]+)['"])""",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(
    r"""url\(\s*['"]?([^'")]+?)['"]?\s*\)""",
    re.IGNORECASE,
)

FONT_EXTENSIONS = {".woff", ".woff2", ".ttf", ".otf", ".eot"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico"}


@dataclass
class CSSResolveResult:
    """Result of CSS dependency resolution."""

    imports_resolved: int = 0
    imports_failed: int = 0
    assets_resolved: int = 0
    assets_failed: int = 0
    fonts_downloaded: list[str] = field(default_factory=list)
    images_downloaded: list[str] = field(default_factory=list)

    @property
    def total_resolved(self) -> int:
        return self.imports_resolved + self.assets_resolved

    @property
    def total_failed(self) -> int:
        return self.imports_failed + self.assets_failed

    def merge(self, other: CSSResolveResult) -> None:
        self.imports_resolved += other.imports_resolved
        self.imports_failed += other.imports_failed
        self.assets_resolved += other.assets_resolved
        self.assets_failed += other.assets_failed
        self.fonts_downloaded.extend(other.fonts_downloaded)
        self.images_downloaded.extend(other.images_downloaded)


class CSSResolver:
    """Recursively resolves and downloads CSS dependencies."""

    def __init__(self, http_session: Any, base_url: str, base_dir: Path):
        self.http_session = http_session
        self.base_url = base_url
        self.base_dir = base_dir
        self._resolved_urls: set[str] = set()

    async def resolve_all(self) -> CSSResolveResult:
        """Resolve all CSS files found in the clone directory."""
        result = CSSResolveResult()
        css_files = list(self.base_dir.rglob("*.css"))
        logger.info("Resolving CSS dependencies in %d files", len(css_files))

        for css_file in css_files:
            file_result = await self._resolve_file(css_file, depth=0)
            result.merge(file_result)

        logger.info(
            "CSS resolution complete: %d resolved, %d failed",
            result.total_resolved,
            result.total_failed,
        )
        return result

    async def _resolve_file(self, css_path: Path, depth: int) -> CSSResolveResult:
        """Resolve dependencies in a single CSS file."""
        result = CSSResolveResult()

        if depth >= MAX_CSS_DEPTH:
            logger.debug("Max CSS depth reached for %s", css_path)
            return result

        try:
            css_text = css_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug("Failed to read CSS file %s: %s", css_path, e)
            return result

        modified = False

        # Process @import statements
        for match in IMPORT_PATTERN.finditer(css_text):
            import_url = match.group(1) or match.group(2)
            if not import_url or import_url.startswith("data:"):
                continue

            abs_url = self._resolve_url(import_url, css_path)
            if abs_url in self._resolved_urls:
                continue
            self._resolved_urls.add(abs_url)

            local_path = self._url_to_local_path(abs_url)
            if not local_path.exists():
                content = await self._download(abs_url)
                if content is not None:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_bytes(content)
                    result.imports_resolved += 1

                    # Recurse into imported CSS
                    sub_result = await self._resolve_file(local_path, depth + 1)
                    result.merge(sub_result)
                else:
                    result.imports_failed += 1

            # Rewrite the @import path to local
            rel_path = self._get_relative_path(css_path, local_path)
            old_text = match.group(0)
            new_text = f'@import url("{rel_path}")'
            css_text = css_text.replace(old_text, new_text, 1)
            modified = True

        # Process url() references (fonts, images, etc.)
        for match in URL_PATTERN.finditer(css_text):
            url_value = match.group(1).strip()
            if not url_value or url_value.startswith("data:"):
                continue
            # Skip already-resolved @import urls
            if url_value in self._resolved_urls:
                continue

            abs_url = self._resolve_url(url_value, css_path)
            if abs_url in self._resolved_urls:
                continue
            self._resolved_urls.add(abs_url)

            local_path = self._url_to_local_path(abs_url)
            if not local_path.exists():
                content = await self._download(abs_url)
                if content is not None:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_bytes(content)
                    result.assets_resolved += 1

                    # Track fonts and images
                    ext = local_path.suffix.lower()
                    if ext in FONT_EXTENSIONS:
                        result.fonts_downloaded.append(str(local_path))
                    elif ext in IMAGE_EXTENSIONS:
                        result.images_downloaded.append(str(local_path))
                else:
                    result.assets_failed += 1

            # Rewrite the url() path to local
            rel_path = self._get_relative_path(css_path, local_path)
            old_text = match.group(0)
            new_text = f"url('{rel_path}')"
            css_text = css_text.replace(old_text, new_text, 1)
            modified = True

        if modified:
            try:
                css_path.write_text(css_text, encoding="utf-8")
            except Exception as e:
                logger.debug("Failed to write updated CSS %s: %s", css_path, e)

        return result

    def _resolve_url(self, url: str, css_path: Path) -> str:
        """Resolve a URL relative to a CSS file's original location."""
        # If absolute URL, return as-is
        if url.startswith(("http://", "https://", "//")):
            if url.startswith("//"):
                url = "https:" + url
            return url

        # If root-relative, join with base_url origin
        if url.startswith("/"):
            parsed = urlparse(self.base_url)
            return f"{parsed.scheme}://{parsed.netloc}{url}"

        # Relative to CSS file — compute original URL from file path
        rel_from_base = css_path.relative_to(self.base_dir)
        original_path = "/" + str(rel_from_base).replace("\\", "/")
        original_url = urljoin(self.base_url, original_path)
        return urljoin(original_url, url)

    def _url_to_local_path(self, url: str) -> Path:
        """Convert an absolute URL to a local filesystem path."""
        parsed = urlparse(url)
        path = parsed.path
        if not path or path == "/":
            path = "/index.css"
        path = path.lstrip("/")
        path = path.replace("../", "").replace("..\\", "")
        return self.base_dir / path

    def _get_relative_path(self, from_file: Path, to_file: Path) -> str:
        """Calculate a relative path from one file to another."""
        try:
            rel = to_file.relative_to(from_file.parent)
            return str(rel).replace("\\", "/")
        except ValueError:
            # Need to go up directories
            from_parts = from_file.parent.parts
            to_parts = to_file.parts
            common = 0
            for a, b in zip(from_parts, to_parts, strict=False):
                if a == b:
                    common += 1
                else:
                    break
            ups = [".."] * (len(from_parts) - common)
            downs = list(to_parts[common:])
            return "/".join(ups + downs)

    async def _download(self, url: str) -> bytes | None:
        """Download a URL and return bytes, or None on failure."""
        try:
            async with self.http_session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data: bytes = await resp.read()
                    return data
                logger.debug("HTTP %d for %s", resp.status, url)
        except Exception as e:
            logger.debug("Download failed for %s: %s", url, e)
        return None
