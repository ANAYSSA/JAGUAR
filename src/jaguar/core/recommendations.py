"""
AI Recommendations Engine for JAGUAR.

Requirement #2: After every scan, generate:
- What is wrong
- Why it is wrong
- How to fix it
- Priority level
- Estimated impact

Analyzes findings across all modules and produces prioritized,
actionable recommendations. Works entirely offline using rule-based
intelligence — no external AI API required (those are optional plugins).
"""

from __future__ import annotations

import logging
from typing import Any

from jaguar.core.models import (
    AnalyzerCategory,
    Finding,
    Priority,
    Recommendation,
    ScanResult,
    Severity,
)

logger = logging.getLogger("jaguar.recommendations")


# ---------------------------------------------------------------------------
# Recommendation rules — maps finding patterns to actionable advice
# ---------------------------------------------------------------------------

# Each rule: (finding_name_pattern, what, why, how, priority, impact_template)
_RULES: list[dict[str, Any]] = [
    # -- Security --
    {
        "category": AnalyzerCategory.SECURITY,
        "pattern": "hsts-not-implemented",
        "what": "HTTP Strict Transport Security (HSTS) is not enabled",
        "why": "Without HSTS, browsers can be tricked into connecting via HTTP, enabling man-in-the-middle attacks and cookie hijacking.",
        "how": "Add the header `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` to your server configuration.",
        "priority": Priority.HIGH,
        "impact": "+20 security points",
    },
    {
        "category": AnalyzerCategory.SECURITY,
        "pattern": "csp-not-implemented",
        "what": "Content Security Policy (CSP) header is missing",
        "why": "CSP prevents cross-site scripting (XSS), clickjacking, and code injection attacks by restricting resource loading origins.",
        "how": "Implement a CSP header starting with `Content-Security-Policy: default-src 'self'` and refine based on your application's needs.",
        "priority": Priority.HIGH,
        "impact": "+25 security points",
    },
    {
        "category": AnalyzerCategory.SECURITY,
        "pattern": "cookies-session-without-secure-flag",
        "what": "Session cookies are missing the Secure flag",
        "why": "Without the Secure flag, session cookies can be transmitted over unencrypted HTTP connections, exposing session tokens to interception.",
        "how": "Set the `Secure` attribute on all session cookies in your server configuration.",
        "priority": Priority.CRITICAL,
        "impact": "+40 security points",
    },
    {
        "category": AnalyzerCategory.SECURITY,
        "pattern": "cookies-session-without-httponly-flag",
        "what": "Session cookies are missing the HttpOnly flag",
        "why": "Without HttpOnly, cookies can be accessed via JavaScript, making them vulnerable to XSS-based session stealing.",
        "how": "Set the `HttpOnly` attribute on all session cookies.",
        "priority": Priority.HIGH,
        "impact": "+30 security points",
    },
    {
        "category": AnalyzerCategory.SECURITY,
        "pattern": "x-frame-options-not-implemented",
        "what": "X-Frame-Options header is not set",
        "why": "Without this header, your site can be embedded in frames on malicious sites, enabling clickjacking attacks.",
        "how": "Add `X-Frame-Options: DENY` or `SAMEORIGIN` header, or use CSP's `frame-ancestors` directive.",
        "priority": Priority.MEDIUM,
        "impact": "+20 security points",
    },
    {
        "category": AnalyzerCategory.SECURITY,
        "pattern": "tls-outdated",
        "what": "TLS protocol version is outdated",
        "why": "Older TLS versions (1.0, 1.1) have known vulnerabilities and are no longer considered secure.",
        "how": "Configure your web server to support only TLS 1.2 and TLS 1.3. Disable SSLv3, TLS 1.0, and TLS 1.1.",
        "priority": Priority.HIGH,
        "impact": "+15 security points",
    },
    {
        "category": AnalyzerCategory.SECURITY,
        "pattern": "certificate-expiring",
        "what": "SSL certificate is expiring soon",
        "why": "An expired certificate will cause browser warnings that destroy user trust and block access.",
        "how": "Renew your SSL certificate. Consider using Let's Encrypt with auto-renewal.",
        "priority": Priority.CRITICAL,
        "impact": "Prevents site downtime",
    },
    # -- SEO --
    {
        "category": AnalyzerCategory.SEO,
        "pattern": "missing-title",
        "what": "Page is missing a title tag",
        "why": "The title tag is the single most important on-page SEO element. Search engines use it as the primary ranking signal and display it in search results.",
        "how": "Add a unique, descriptive `<title>` tag (50-60 characters) to every page.",
        "priority": Priority.CRITICAL,
        "impact": "+15 SEO points",
    },
    {
        "category": AnalyzerCategory.SEO,
        "pattern": "missing-meta-description",
        "what": "Meta description tag is missing",
        "why": "Meta descriptions appear in search results and significantly influence click-through rates.",
        "how": 'Add a compelling `<meta name="description" content="...">` tag (150-160 characters) to every page.',
        "priority": Priority.HIGH,
        "impact": "+10 SEO points",
    },
    {
        "category": AnalyzerCategory.SEO,
        "pattern": "missing-canonical",
        "what": "Canonical URL tag is missing",
        "why": "Without a canonical tag, search engines may index duplicate versions of your page, diluting ranking signals.",
        "how": 'Add `<link rel="canonical" href="...">` pointing to the preferred URL.',
        "priority": Priority.MEDIUM,
        "impact": "+5 SEO points",
    },
    {
        "category": AnalyzerCategory.SEO,
        "pattern": "missing-sitemap",
        "what": "No sitemap.xml found",
        "why": "Sitemaps help search engines discover and index all important pages on your site.",
        "how": "Generate a sitemap.xml and submit it to Google Search Console and Bing Webmaster Tools.",
        "priority": Priority.MEDIUM,
        "impact": "+5 SEO points",
    },
    {
        "category": AnalyzerCategory.SEO,
        "pattern": "missing-og",
        "what": "Open Graph tags are missing",
        "why": "Open Graph tags control how your pages appear when shared on social media. Without them, platforms display generic previews.",
        "how": "Add og:title, og:description, og:image, and og:url meta tags to all important pages.",
        "priority": Priority.MEDIUM,
        "impact": "+5 SEO points",
    },
    # -- Performance --
    {
        "category": AnalyzerCategory.PERFORMANCE,
        "pattern": "no-compression",
        "what": "Server is not using compression",
        "why": "Without gzip/brotli compression, page sizes are unnecessarily large, increasing load times by 3-5x for text resources.",
        "how": "Enable gzip or brotli compression on your web server for text-based resources (HTML, CSS, JS, JSON, SVG).",
        "priority": Priority.HIGH,
        "impact": "+15 performance points, 60-80% size reduction",
    },
    {
        "category": AnalyzerCategory.PERFORMANCE,
        "pattern": "no-cache-headers",
        "what": "Cache headers are not configured",
        "why": "Without proper caching, browsers re-download resources on every visit, wasting bandwidth and increasing load times.",
        "how": "Set `Cache-Control` headers: use long max-age for static assets (CSS, JS, images) and shorter max-age for HTML.",
        "priority": Priority.MEDIUM,
        "impact": "+10 performance points",
    },
    {
        "category": AnalyzerCategory.PERFORMANCE,
        "pattern": "large-page-size",
        "what": "Total page size exceeds recommended limits",
        "why": "Large pages load slowly, especially on mobile devices with limited bandwidth, hurting user experience and search ranking.",
        "how": "Optimize images (use WebP/AVIF), minify CSS/JS, lazy-load below-the-fold content, and remove unused code.",
        "priority": Priority.HIGH,
        "impact": "+10 performance points",
    },
    # -- Accessibility --
    {
        "category": AnalyzerCategory.ACCESSIBILITY,
        "pattern": "images-missing-alt",
        "what": "Images are missing alt text",
        "why": "Screen readers rely on alt text to describe images to visually impaired users. Missing alt text makes content inaccessible.",
        "how": 'Add descriptive `alt` attributes to all `<img>` tags. Decorative images should use `alt=""`.',
        "priority": Priority.HIGH,
        "impact": "+10 accessibility points",
    },
    {
        "category": AnalyzerCategory.ACCESSIBILITY,
        "pattern": "low-contrast",
        "what": "Text has insufficient color contrast",
        "why": "Low contrast text is difficult or impossible to read for users with visual impairments (WCAG 2.1 requires 4.5:1 ratio).",
        "how": "Increase the contrast ratio between text and background colors. Use a contrast checker tool to verify WCAG compliance.",
        "priority": Priority.HIGH,
        "impact": "+15 accessibility points",
    },
    # -- UX --
    {
        "category": AnalyzerCategory.UX,
        "pattern": "no-mobile-viewport",
        "what": "Mobile viewport meta tag is missing",
        "why": "Without the viewport tag, mobile browsers render the page at desktop width and scale down, making it unusable on phones.",
        "how": 'Add `<meta name="viewport" content="width=device-width, initial-scale=1">` to the page head.',
        "priority": Priority.CRITICAL,
        "impact": "+20 UX points",
    },
    {
        "category": AnalyzerCategory.UX,
        "pattern": "poor-readability",
        "what": "Text readability score is poor",
        "why": "Complex, hard-to-read text increases bounce rates and reduces engagement.",
        "how": "Use shorter sentences, simpler words, and break up large text blocks. Aim for a Flesch Reading Ease score above 60.",
        "priority": Priority.MEDIUM,
        "impact": "+10 UX points",
    },
]


def generate_recommendations(scan_result: ScanResult) -> list[Recommendation]:
    """
    Generate prioritized recommendations from scan results.

    Examines all analyzer findings and matches them against
    the recommendation rules to produce actionable advice.
    """
    recommendations: list[Recommendation] = []
    seen_patterns: set[str] = set()

    for _analyzer_name, analyzer_result in scan_result.analyzer_results.items():
        for finding in analyzer_result.findings:
            if finding.passed:
                continue

            # Try rule-based matching
            matched = _match_rules(finding, analyzer_result.category)
            for rec in matched:
                key = f"{rec.category}:{rec.what}"
                if key not in seen_patterns:
                    seen_patterns.add(key)
                    recommendations.append(rec)

            # Generate generic recommendation for unmatched failed findings
            if not matched:
                generic = _generic_recommendation(finding, analyzer_result.category)
                key = f"{generic.category}:{generic.what}"
                if key not in seen_patterns:
                    seen_patterns.add(key)
                    recommendations.append(generic)

    # Sort by priority (critical first, then high, medium, low)
    priority_order = {
        Priority.CRITICAL: 0,
        Priority.HIGH: 1,
        Priority.MEDIUM: 2,
        Priority.LOW: 3,
    }
    recommendations.sort(key=lambda r: priority_order.get(r.priority, 4))

    return recommendations


def _match_rules(
    finding: Finding,
    category: AnalyzerCategory,
) -> list[Recommendation]:
    """Match a finding against recommendation rules."""
    matches: list[Recommendation] = []

    for rule in _RULES:
        if rule["category"] != category:
            continue

        pattern = rule["pattern"]
        if pattern in finding.name or finding.name.startswith(pattern):
            matches.append(
                Recommendation(
                    what=rule["what"],
                    why=rule["why"],
                    how=rule["how"],
                    priority=rule["priority"],
                    estimated_impact=rule["impact"],
                    category=category,
                    related_findings=[finding.name],
                )
            )

    return matches


def _generic_recommendation(
    finding: Finding,
    category: AnalyzerCategory,
) -> Recommendation:
    """Generate a generic recommendation for an unmatched finding."""
    priority_map = {
        Severity.CRITICAL: Priority.CRITICAL,
        Severity.HIGH: Priority.HIGH,
        Severity.MEDIUM: Priority.MEDIUM,
        Severity.LOW: Priority.LOW,
        Severity.INFO: Priority.LOW,
    }

    impact = abs(finding.score_modifier) if finding.score_modifier < 0 else 5

    return Recommendation(
        what=finding.title,
        why=finding.description or f"This check failed during {category.value} analysis.",
        how=finding.recommendation
        or f"Address the {finding.title.lower()} issue identified in the scan.",
        priority=priority_map.get(finding.severity, Priority.MEDIUM),
        estimated_impact=f"+{impact} {category.value} points",
        category=category,
        related_findings=[finding.name],
    )


def generate_executive_summary(scan_result: ScanResult) -> str:
    """
    Generate an executive summary paragraph for the scan results.

    Provides a high-level overview suitable for non-technical stakeholders.
    """
    url = scan_result.url
    overall = scan_result.overall_score

    if overall is None:
        return f"Scan of {url} completed but no overall score was computed."

    score = overall.score
    grade = overall.grade.value

    # Count issues by severity
    critical = 0
    high = 0
    medium = 0
    low = 0

    for ar in scan_result.analyzer_results.values():
        for f in ar.findings:
            if not f.passed:
                match f.severity:
                    case Severity.CRITICAL:
                        critical += 1
                    case Severity.HIGH:
                        high += 1
                    case Severity.MEDIUM:
                        medium += 1
                    case Severity.LOW:
                        low += 1

    total_issues = critical + high + medium + low

    # Build summary
    lines = [
        f"JAGUAR scanned {url} and assigned an overall grade of **{grade}** ({score}/100).",
    ]

    if total_issues == 0:
        lines.append("No issues were found — this site meets all analyzed criteria.")
    else:
        parts = []
        if critical:
            parts.append(f"{critical} critical")
        if high:
            parts.append(f"{high} high")
        if medium:
            parts.append(f"{medium} medium")
        if low:
            parts.append(f"{low} low")
        lines.append(
            f"A total of {total_issues} issues were identified: {', '.join(parts)} severity."
        )

    # Highlight worst categories
    worst: list[tuple[str, int]] = []
    for name, ar in scan_result.analyzer_results.items():
        if ar.score < 70:
            worst.append((name, ar.score))
    worst.sort(key=lambda x: x[1])

    if worst:
        labels = [f"{n.replace('_', ' ').title()} ({s}/100)" for n, s in worst[:3]]
        lines.append(f"Areas needing the most attention: {', '.join(labels)}.")

    # Top recommendations
    if scan_result.recommendations:
        top = scan_result.recommendations[:3]
        lines.append("Top recommendations:")
        for i, rec in enumerate(top, 1):
            lines.append(f"  {i}. {rec.what} ({rec.estimated_impact})")

    return " ".join(lines)
