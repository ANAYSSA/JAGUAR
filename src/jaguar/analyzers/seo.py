"""
SEO analyzer for JAGUAR.

Checks: title, description, Open Graph, canonical, robots,
sitemap, structured data, heading hierarchy, image alt text.
"""

from __future__ import annotations

import logging
import re

from jaguar.analyzers.base import BaseAnalyzer
from jaguar.core.models import AnalyzerCategory, Finding, ScanContext, Severity

logger = logging.getLogger("jaguar.analyzers.seo")


class SEOAnalyzer(BaseAnalyzer):
    """SEO analysis module."""

    name = "seo"
    category = AnalyzerCategory.SEO
    weight = 1.0

    async def _run_checks(self, context: ScanContext) -> list[Finding]:
        html = context.response_body
        findings: list[Finding] = []

        findings.append(self._check_title(html))
        findings.append(self._check_meta_description(html))
        findings.append(self._check_canonical(html))
        findings.extend(self._check_open_graph(html))
        findings.append(self._check_robots_meta(html))
        findings.append(await self._check_robots_txt(context))
        findings.append(await self._check_sitemap(context))
        findings.append(self._check_structured_data(html))
        findings.append(self._check_heading_hierarchy(html))
        findings.append(self._check_image_alt_text(html))
        findings.append(self._check_lang_attribute(html))
        findings.append(self._check_meta_viewport(html))

        return findings

    def _check_title(self, html: str) -> Finding:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if not match or not match.group(1).strip():
            return Finding(
                name="missing-title",
                title="Missing Title Tag",
                description="No <title> tag found. This is the most critical on-page SEO element.",
                passed=False,
                severity=Severity.CRITICAL,
                score_modifier=-20,
                recommendation="Add a unique, descriptive <title> tag (50-60 chars) to every page.",
            )
        title = match.group(1).strip()
        length = len(title)
        if length < 10:
            return Finding(
                name="title-too-short",
                title="Title Too Short",
                description=f"Title is only {length} characters: '{title}'.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-10,
                data={"title": title, "length": length},
                recommendation="Write a descriptive title of 50-60 characters.",
            )
        if length > 70:
            return Finding(
                name="title-too-long",
                title="Title Too Long",
                description=f"Title is {length} characters and may be truncated in search results.",
                passed=False,
                severity=Severity.LOW,
                score_modifier=-5,
                data={"title": title, "length": length},
                recommendation="Shorten the title to 50-60 characters.",
            )
        return Finding(
            name="title-present",
            title="Title Tag Present",
            description=f"Title: '{title}' ({length} chars).",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={"title": title, "length": length},
        )

    def _check_meta_description(self, html: str) -> Finding:
        match = re.search(
            r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r'<meta\s+content=["\']([^"\']*?)["\']\s+name=["\']description["\']',
                html,
                re.IGNORECASE,
            )
        if not match or not match.group(1).strip():
            return Finding(
                name="missing-meta-description",
                title="Missing Meta Description",
                description="No meta description found. This affects click-through rates in search results.",
                passed=False,
                severity=Severity.HIGH,
                score_modifier=-10,
                recommendation="Add <meta name='description' content='...'> (150-160 chars).",
            )
        desc = match.group(1).strip()
        length = len(desc)
        if length < 50:
            return Finding(
                name="meta-description-short",
                title="Meta Description Too Short",
                description=f"Meta description is only {length} characters.",
                passed=False,
                severity=Severity.LOW,
                score_modifier=-5,
                data={"description": desc, "length": length},
                recommendation="Write a compelling description of 150-160 characters.",
            )
        return Finding(
            name="meta-description-present",
            title="Meta Description Present",
            description=f"Description ({length} chars): '{desc[:80]}...'",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={"description": desc, "length": length},
        )

    def _check_canonical(self, html: str) -> Finding:
        match = re.search(
            r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', html, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'<link[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\']',
                html,
                re.IGNORECASE,
            )
        if not match:
            return Finding(
                name="missing-canonical",
                title="Missing Canonical URL",
                description="No canonical URL tag found. This can lead to duplicate content issues.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-5,
                recommendation="Add <link rel='canonical' href='...'> to specify the preferred URL.",
            )
        return Finding(
            name="canonical-present",
            title="Canonical URL Set",
            description=f"Canonical URL: {match.group(1)}",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={"canonical": match.group(1)},
        )

    def _check_open_graph(self, html: str) -> list[Finding]:
        findings: list[Finding] = []
        og_tags = {"og:title": None, "og:description": None, "og:image": None, "og:url": None}
        for tag in og_tags:
            match = re.search(
                rf'<meta\s+(?:property|name)=["\']({re.escape(tag)})["\'][^>]*content=["\']([^"\']*)["\']',
                html,
                re.IGNORECASE,
            )
            if not match:
                match = re.search(
                    rf'<meta\s+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']({re.escape(tag)})["\']',
                    html,
                    re.IGNORECASE,
                )
                if match:
                    og_tags[tag] = match.group(1)  # type: ignore
            else:
                og_tags[tag] = match.group(2)  # type: ignore

        missing = [k for k, v in og_tags.items() if not v]
        if missing:
            findings.append(
                Finding(
                    name="missing-og",
                    title="Missing Open Graph Tags",
                    description=f"Missing: {', '.join(missing)}",
                    passed=False,
                    severity=Severity.MEDIUM,
                    score_modifier=-5,
                    data={"missing": missing, "present": {k: v for k, v in og_tags.items() if v}},
                    recommendation="Add all Open Graph tags for proper social media previews.",
                )
            )
        else:
            findings.append(
                Finding(
                    name="og-complete",
                    title="Open Graph Tags Complete",
                    description="All essential Open Graph tags are present.",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=5,
                    data={"tags": og_tags},
                )
            )
        return findings

    def _check_robots_meta(self, html: str) -> Finding:
        match = re.search(
            r'<meta\s+name=["\']robots["\']\s+content=["\']([^"\']*)["\']',
            html,
            re.IGNORECASE,
        )
        if not match:
            return Finding(
                name="robots-meta-not-set",
                title="Robots Meta Not Set",
                description="No robots meta tag. Search engines will index by default.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )
        content = match.group(1).lower()
        if "noindex" in content:
            return Finding(
                name="robots-noindex",
                title="Page Set to NoIndex",
                description="The robots meta tag contains 'noindex'. This page will not appear in search results.",
                passed=False,
                severity=Severity.HIGH,
                score_modifier=-15,
                data={"content": content},
                recommendation="Remove 'noindex' unless this page should intentionally be excluded from search.",
            )
        return Finding(
            name="robots-meta-ok",
            title="Robots Meta Tag OK",
            description=f"Robots directives: {content}",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={"content": content},
        )

    async def _check_robots_txt(self, ctx: ScanContext) -> Finding:
        from jaguar.core.http_client import HttpClient

        try:
            async with HttpClient() as http:
                robots_url = f"{ctx.base_url}/robots.txt"
                resp = await http.get(robots_url)
                if resp.status == 200 and "user-agent" in resp.body.lower():
                    return Finding(
                        name="robots-txt-present",
                        title="robots.txt Present",
                        description="A valid robots.txt file was found.",
                        passed=True,
                        severity=Severity.INFO,
                        score_modifier=0,
                    )
        except Exception:
            pass
        return Finding(
            name="missing-robots-txt",
            title="robots.txt Missing",
            description="No valid robots.txt found.",
            passed=False,
            severity=Severity.LOW,
            score_modifier=-3,
            recommendation="Create a robots.txt file to guide search engine crawlers.",
        )

    async def _check_sitemap(self, ctx: ScanContext) -> Finding:
        from jaguar.core.http_client import HttpClient

        try:
            async with HttpClient() as http:
                for path in ["/sitemap.xml", "/sitemap_index.xml"]:
                    url = f"{ctx.base_url}{path}"
                    resp = await http.get(url)
                    if resp.status == 200 and (
                        "<?xml" in resp.body
                        or "<urlset" in resp.body
                        or "<sitemapindex" in resp.body
                    ):
                        return Finding(
                            name="sitemap-present",
                            title="Sitemap Found",
                            description=f"Sitemap found at {path}.",
                            passed=True,
                            severity=Severity.INFO,
                            score_modifier=5,
                            data={"path": path},
                        )
        except Exception:
            pass
        return Finding(
            name="missing-sitemap",
            title="Sitemap Not Found",
            description="No sitemap.xml found.",
            passed=False,
            severity=Severity.MEDIUM,
            score_modifier=-5,
            recommendation="Create and submit a sitemap.xml for better indexing.",
        )

    def _check_structured_data(self, html: str) -> Finding:
        has_jsonld = bool(
            re.search(r'<script\s+type=["\']application/ld\+json["\']', html, re.IGNORECASE)
        )
        has_microdata = bool(re.search(r"itemscope|itemtype", html, re.IGNORECASE))
        if has_jsonld or has_microdata:
            fmt = "JSON-LD" if has_jsonld else "Microdata"
            return Finding(
                name="structured-data-present",
                title="Structured Data Found",
                description=f"Structured data detected ({fmt}).",
                passed=True,
                severity=Severity.INFO,
                score_modifier=5,
                data={"format": fmt},
            )
        return Finding(
            name="missing-structured-data",
            title="No Structured Data",
            description="No JSON-LD or Microdata found.",
            passed=False,
            severity=Severity.LOW,
            score_modifier=-3,
            recommendation="Add structured data (JSON-LD) for rich search results.",
        )

    def _check_heading_hierarchy(self, html: str) -> Finding:
        headings = re.findall(r"<(h[1-6])[^>]*>(.*?)</\1>", html, re.IGNORECASE | re.DOTALL)
        h1_count = sum(1 for tag, _ in headings if tag.lower() == "h1")
        if h1_count == 0:
            return Finding(
                name="missing-h1",
                title="No H1 Tag",
                description="No H1 heading found on the page.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-10,
                recommendation="Add a single, descriptive H1 tag to every page.",
            )
        if h1_count > 1:
            return Finding(
                name="multiple-h1",
                title="Multiple H1 Tags",
                description=f"Found {h1_count} H1 tags. Use a single H1 per page.",
                passed=False,
                severity=Severity.LOW,
                score_modifier=-5,
                recommendation="Use a single H1 per page for proper heading hierarchy.",
            )
        return Finding(
            name="heading-hierarchy-ok",
            title="Heading Hierarchy OK",
            description=f"Single H1 found. {len(headings)} total headings.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
        )

    def _check_image_alt_text(self, html: str) -> Finding:
        images = re.findall(r"<img\s[^>]*>", html, re.IGNORECASE)
        if not images:
            return Finding(
                name="no-images",
                title="No Images Found",
                description="No images on the page.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )
        missing = sum(1 for img in images if not re.search(r'alt=["\']', img, re.IGNORECASE))
        pct = (missing / len(images)) * 100 if images else 0
        if missing > 0:
            return Finding(
                name="images-missing-alt",
                title="Images Missing Alt Text",
                description=f"{missing}/{len(images)} images ({pct:.0f}%) lack alt text.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-min(10, missing * 2),
                recommendation="Add descriptive alt attributes to all images.",
            )
        return Finding(
            name="images-alt-complete",
            title="All Images Have Alt Text",
            description=f"All {len(images)} images have alt attributes.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
        )

    def _check_lang_attribute(self, html: str) -> Finding:
        match = re.search(r'<html[^>]*\slang=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if match:
            return Finding(
                name="lang-attribute-present",
                title="Language Attribute Set",
                description=f"HTML lang attribute set to '{match.group(1)}'.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )
        return Finding(
            name="missing-lang",
            title="Missing Language Attribute",
            description="HTML element lacks a lang attribute.",
            passed=False,
            severity=Severity.LOW,
            score_modifier=-3,
            recommendation="Add lang='en' (or appropriate language) to the <html> tag.",
        )

    def _check_meta_viewport(self, html: str) -> Finding:
        match = re.search(r'<meta\s+name=["\']viewport["\']', html, re.IGNORECASE)
        if match:
            return Finding(
                name="viewport-meta-present",
                title="Viewport Meta Tag Set",
                description="Mobile viewport meta tag is configured.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )
        return Finding(
            name="no-mobile-viewport",
            title="Missing Viewport Meta",
            description="No viewport meta tag — the page will not render properly on mobile.",
            passed=False,
            severity=Severity.HIGH,
            score_modifier=-10,
            recommendation="Add <meta name='viewport' content='width=device-width, initial-scale=1'>.",
        )
