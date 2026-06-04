"""
Link rewriting logic for the website cloner.

Converts absolute and relative URLs into local filesystem paths
so the cloned website can be browsed offline.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger("jaguar.cloner.rewriter")


class LinkRewriter:
    """Rewrites HTML links to point to local files."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.base_parsed = urlparse(base_url)

    def rewrite_html(self, html: str, current_url: str) -> str:
        """Parse HTML and rewrite links for local browsing."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Rewrite <a> hrefs
            for a in soup.find_all("a", href=True):
                a["href"] = self._rewrite_url(a["href"], current_url, is_asset=False)

            # Rewrite asset URLs (<link>, <script>, <img>)
            for link in soup.find_all("link", href=True):
                link["href"] = self._rewrite_url(link["href"], current_url, is_asset=True)

            for script in soup.find_all("script", src=True):
                script["src"] = self._rewrite_url(script["src"], current_url, is_asset=True)

            for img in soup.find_all("img", src=True):
                img["src"] = self._rewrite_url(img["src"], current_url, is_asset=True)

            return str(soup)

        except Exception as e:
            logger.error("Failed to rewrite HTML for %s: %s", current_url, e)
            return html

    def rewrite_css(self, css: str, current_url: str) -> str:
        """Rewrite url() references in CSS files."""

        def replace_url(match: re.Match) -> str:  # type: ignore
            original = match.group(1)
            # Remove quotes
            cleaned = original.strip("'\"")

            # Skip data URIs
            if cleaned.startswith("data:"):
                return match.group(0)  # type: ignore

            rewritten = self._rewrite_url(cleaned, current_url, is_asset=True)
            return f"url('{rewritten}')"

        return re.sub(r"url\(([^)]+)\)", replace_url, css)

    def _rewrite_url(self, url: str, current_url: str, is_asset: bool) -> str:
        """Convert a URL to a local relative path."""
        # Skip special schemes
        if url.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
            return url

        # Resolve relative URLs
        absolute = urljoin(current_url, url)
        parsed = urlparse(absolute)

        # External links
        if parsed.netloc != self.base_parsed.netloc:
            # We don't download external assets by default, so keep absolute
            return absolute

        # Build local path
        path = parsed.path
        if not path or path == "/":
            path = "/index.html"

        # Ensure HTML files have extension
        if not is_asset and not path.split("/")[-1].count("."):
            if not path.endswith("/"):
                path += "/index.html"
            else:
                path += "index.html"

        # Handle query parameters (strip them for local files, or encode)
        # For simplicity, we strip them and rely on the path

        # Calculate relative path from current_url to the target path
        current_path = urlparse(current_url).path
        if not current_path or current_path == "/":
            current_path = "/index.html"

        return self._get_relative_path(current_path, path)

    def _get_relative_path(self, from_path: str, to_path: str) -> str:
        """Calculate relative path traversal."""
        from_parts = [p for p in from_path.split("/") if p]
        to_parts = [p for p in to_path.split("/") if p]

        # Remove filename from from_parts
        if from_parts:
            from_parts.pop()

        # Find common prefix
        common = 0
        for f, t in zip(from_parts, to_parts, strict=False):
            if f == t:
                common += 1
            else:
                break

        # Build path: up directory + remaining target path
        ups = [".."] * (len(from_parts) - common)
        downs = to_parts[common:]

        rel_path = "/".join(ups + downs)
        return unquote(rel_path) or "./"
