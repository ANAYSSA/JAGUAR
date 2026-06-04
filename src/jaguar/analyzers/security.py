"""
Security analyzer for JAGUAR.

Comprehensive security audit covering:
- TLS/SSL certificate validity and configuration
- HSTS (HTTP Strict Transport Security)
- CSP (Content Security Policy)
- Cookie security (Secure, HttpOnly, SameSite)
- CORS (Cross-Origin Resource Sharing)
- Referrer Policy
- Permissions Policy
- X-Frame-Options
- X-Content-Type-Options
- X-XSS-Protection (deprecated but checked)
- Redirect chain security

Inspired by Mozilla HTTP Observatory's analyzer architecture but
reimplemented as a unified async Python module with expanded checks.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from jaguar.analyzers.base import BaseAnalyzer
from jaguar.core.models import (
    AnalyzerCategory,
    Finding,
    ScanContext,
    Severity,
)
from jaguar.utils.crypto import evaluate_cipher_suite, evaluate_tls_protocol

logger = logging.getLogger("jaguar.analyzers.security")


class SecurityAnalyzer(BaseAnalyzer):
    """Comprehensive website security analyzer."""

    name = "security"
    category = AnalyzerCategory.SECURITY
    weight = 1.5

    async def _run_checks(self, context: ScanContext) -> list[Finding]:
        findings: list[Finding] = []

        findings.append(self._check_https(context))
        findings.append(self._check_tls(context))
        findings.append(self._check_certificate(context))
        findings.append(self._check_hsts(context))
        findings.append(self._check_csp(context))
        findings.extend(self._check_cookies(context))
        findings.append(self._check_cors(context))
        findings.append(self._check_referrer_policy(context))
        findings.append(self._check_permissions_policy(context))
        findings.append(self._check_x_frame_options(context))
        findings.append(self._check_x_content_type_options(context))
        findings.append(self._check_x_xss_protection(context))
        findings.append(self._check_redirect_security(context))

        return findings

    # -- Individual checks --

    def _check_https(self, ctx: ScanContext) -> Finding:
        """Check if the site is served over HTTPS."""
        is_https = urlparse(ctx.final_url or ctx.url).scheme == "https"

        return Finding(
            name="https-enabled",
            title="HTTPS Enabled",
            description="Site is served over a secure HTTPS connection."
            if is_https
            else "Site is not served over HTTPS — all data is transmitted in plain text.",
            passed=is_https,
            severity=Severity.CRITICAL if not is_https else Severity.INFO,
            score_modifier=0 if is_https else -30,
            recommendation=""
            if is_https
            else "Configure your web server to serve all content over HTTPS. Obtain a free certificate from Let's Encrypt.",
        )

    def _check_tls(self, ctx: ScanContext) -> Finding:
        """Check TLS protocol version and cipher suite."""
        tls = ctx.tls_info
        protocol = tls.get("protocol", "")
        cipher = tls.get("cipher", ("", "", 0))

        if not protocol:
            return Finding(
                name="tls-info-unavailable",
                title="TLS Information",
                description="TLS protocol information could not be determined.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )

        cipher_name = cipher[0] if isinstance(cipher, (tuple, list)) else str(cipher)
        proto_eval = evaluate_tls_protocol(protocol)
        cipher_eval = evaluate_cipher_suite(cipher_name)

        passed = proto_eval["secure"] and cipher_eval["secure"]
        modifier = 0
        if not proto_eval["secure"]:
            modifier -= 15
        if not cipher_eval["secure"]:
            modifier -= 10

        return Finding(
            name="tls-protocol" if passed else "tls-outdated",
            title="TLS Protocol & Cipher",
            description=f"{proto_eval['message']} {cipher_eval['message']}",
            passed=passed,
            severity=Severity.HIGH if not passed else Severity.INFO,
            score_modifier=modifier,
            data={"protocol": protocol, "cipher": cipher_name},
            recommendation=""
            if passed
            else "Upgrade to TLS 1.2 or 1.3 and use strong cipher suites (AES-GCM, ChaCha20-Poly1305).",
        )

    def _check_certificate(self, ctx: ScanContext) -> Finding:
        """Check SSL certificate validity and expiration."""
        tls = ctx.tls_info

        if not tls.get("not_after"):
            return Finding(
                name="certificate-info-unavailable",
                title="SSL Certificate",
                description="Certificate information could not be determined.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )

        days = tls.get("days_until_expiry")
        expired = tls.get("expired", False)

        if expired:
            return Finding(
                name="certificate-expired",
                title="SSL Certificate Expired",
                description="The SSL certificate has expired, causing browser security warnings.",
                passed=False,
                severity=Severity.CRITICAL,
                score_modifier=-30,
                recommendation="Renew your SSL certificate immediately.",
            )

        if days is not None and days < 30:
            return Finding(
                name="certificate-expiring",
                title="SSL Certificate Expiring Soon",
                description=f"Certificate expires in {days} days.",
                passed=False,
                severity=Severity.HIGH,
                score_modifier=-10,
                recommendation="Renew your SSL certificate. Consider auto-renewal with Let's Encrypt.",
            )

        return Finding(
            name="certificate-valid",
            title="SSL Certificate Valid",
            description=f"Certificate is valid with {days} days until expiration."
            if days
            else "Certificate is valid.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={"days_until_expiry": days},
        )

    def _check_hsts(self, ctx: ScanContext) -> Finding:
        """Check HTTP Strict Transport Security header."""
        hsts = ctx.response_headers.get("Strict-Transport-Security", "")

        if not hsts:
            return Finding(
                name="hsts-not-implemented",
                title="HSTS Not Implemented",
                description="HTTP Strict Transport Security header is not set. Browsers can be downgraded to HTTP.",
                passed=False,
                severity=Severity.HIGH,
                score_modifier=-20,
                recommendation="Add 'Strict-Transport-Security: max-age=31536000; includeSubDomains; preload' header.",
            )

        try:
            directives = [d.strip().lower() for d in hsts.split(";")]
            max_age = None
            include_subdomains = False
            preload = False

            for d in directives:
                if d.startswith("max-age="):
                    max_age = int(d.split("=")[1])
                elif d == "includesubdomains":
                    include_subdomains = True
                elif d == "preload":
                    preload = True

            if max_age is None:
                return Finding(
                    name="hsts-header-invalid",
                    title="HSTS Header Invalid",
                    description="HSTS header is present but cannot be parsed.",
                    passed=False,
                    severity=Severity.MEDIUM,
                    score_modifier=-20,
                    recommendation="Fix the Strict-Transport-Security header format.",
                )

            six_months = 15552000
            if max_age < six_months:
                return Finding(
                    name="hsts-short-max-age",
                    title="HSTS Max-Age Too Short",
                    description=f"HSTS max-age is {max_age}s ({max_age // 86400} days). Minimum recommended is 6 months.",
                    passed=False,
                    severity=Severity.MEDIUM,
                    score_modifier=-10,
                    data={"max_age": max_age},
                    recommendation="Increase HSTS max-age to at least 31536000 (1 year).",
                )

            modifier = 0
            if preload and include_subdomains:
                modifier = 5  # Extra credit

            return Finding(
                name="hsts-implemented",
                title="HSTS Implemented",
                description=f"HSTS enabled with max-age={max_age}s. includeSubDomains={include_subdomains}, preload={preload}.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=modifier,
                data={
                    "max_age": max_age,
                    "includeSubDomains": include_subdomains,
                    "preload": preload,
                },
            )

        except (ValueError, IndexError):
            return Finding(
                name="hsts-header-invalid",
                title="HSTS Header Invalid",
                description="HSTS header cannot be parsed.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-20,
                recommendation="Fix the Strict-Transport-Security header format.",
            )

    def _check_csp(self, ctx: ScanContext) -> Finding:
        """Check Content Security Policy header."""
        csp = ctx.response_headers.get("Content-Security-Policy", "")

        if not csp:
            return Finding(
                name="csp-not-implemented",
                title="CSP Not Implemented",
                description="Content Security Policy header is missing. The site is vulnerable to XSS and code injection.",
                passed=False,
                severity=Severity.HIGH,
                score_modifier=-25,
                recommendation="Implement a Content Security Policy. Start with: Content-Security-Policy: default-src 'self'",
            )

        # Parse CSP directives
        directives: dict[str, str] = {}
        for part in csp.split(";"):
            part = part.strip()
            if " " in part:
                key, value = part.split(" ", 1)
                directives[key.lower()] = value
            elif part:
                directives[part.lower()] = ""

        # Check for unsafe directives
        unsafe_issues: list[str] = []
        script_src = directives.get("script-src", directives.get("default-src", "*"))

        if "'unsafe-inline'" in script_src:
            unsafe_issues.append("'unsafe-inline' in script-src allows inline scripts")
        if "'unsafe-eval'" in script_src:
            unsafe_issues.append("'unsafe-eval' in script-src allows eval()")
        if script_src.strip() == "*" or script_src.strip() == "https:":
            unsafe_issues.append("Overly broad script source allows loading from any origin")

        if unsafe_issues:
            return Finding(
                name="csp-implemented-with-unsafe",
                title="CSP Implemented (with unsafe directives)",
                description="CSP is set but contains unsafe directives: "
                + "; ".join(unsafe_issues),
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-10,
                data={"directives": directives, "issues": unsafe_issues},
                recommendation="Remove 'unsafe-inline' and 'unsafe-eval'. Use nonces or hashes instead.",
            )

        return Finding(
            name="csp-implemented",
            title="CSP Implemented",
            description="Content Security Policy is properly configured.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=5,
            data={"directives": directives},
        )

    def _check_cookies(self, ctx: ScanContext) -> list[Finding]:
        """Check cookie security attributes."""
        findings: list[Finding] = []

        if not ctx.cookies:
            findings.append(
                Finding(
                    name="cookies-not-found",
                    title="No Cookies Set",
                    description="No cookies were detected.",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=0,
                )
            )
            return findings

        insecure_cookies: list[str] = []
        no_httponly: list[str] = []
        no_samesite: list[str] = []

        for cookie in ctx.cookies:
            name = cookie.get("name", "unknown")
            is_session = any(k in name.lower() for k in ("sess", "login", "auth", "token"))

            if not cookie.get("secure"):
                insecure_cookies.append(name)
            if is_session and not cookie.get("httponly"):
                no_httponly.append(name)
            if not cookie.get("samesite"):
                no_samesite.append(name)

        if insecure_cookies:
            findings.append(
                Finding(
                    name="cookies-without-secure-flag",
                    title="Cookies Missing Secure Flag",
                    description=f"Cookies without Secure flag: {', '.join(insecure_cookies[:5])}",
                    passed=False,
                    severity=Severity.HIGH,
                    score_modifier=-15,
                    recommendation="Set the Secure attribute on all cookies.",
                )
            )

        if no_httponly:
            findings.append(
                Finding(
                    name="cookies-session-without-httponly-flag",
                    title="Session Cookies Missing HttpOnly",
                    description=f"Session cookies without HttpOnly: {', '.join(no_httponly[:5])}",
                    passed=False,
                    severity=Severity.HIGH,
                    score_modifier=-20,
                    recommendation="Set the HttpOnly attribute on all session cookies.",
                )
            )

        if no_samesite:
            findings.append(
                Finding(
                    name="cookies-without-samesite",
                    title="Cookies Missing SameSite",
                    description=f"Cookies without SameSite attribute: {', '.join(no_samesite[:5])}",
                    passed=False,
                    severity=Severity.MEDIUM,
                    score_modifier=-5,
                    recommendation="Set SameSite=Lax or SameSite=Strict on all cookies.",
                )
            )

        if not insecure_cookies and not no_httponly:
            findings.append(
                Finding(
                    name="cookies-secure",
                    title="Cookies Properly Secured",
                    description="All cookies have appropriate security attributes.",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=5,
                )
            )

        return findings

    def _check_cors(self, ctx: ScanContext) -> Finding:
        """Check Cross-Origin Resource Sharing headers."""
        acao = ctx.response_headers.get("Access-Control-Allow-Origin", "")

        if not acao:
            return Finding(
                name="cors-not-implemented",
                title="CORS Not Configured",
                description="No CORS headers present. Content is not shared cross-origin.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )

        if acao == "*":
            acac = ctx.response_headers.get("Access-Control-Allow-Credentials", "").lower()
            if acac == "true":
                return Finding(
                    name="cors-universal-with-credentials",
                    title="CORS Allows Universal Access with Credentials",
                    description="CORS is configured to allow any origin with credentials — critical security risk.",
                    passed=False,
                    severity=Severity.CRITICAL,
                    score_modifier=-30,
                    recommendation="Never combine Access-Control-Allow-Origin: * with Access-Control-Allow-Credentials: true.",
                )
            return Finding(
                name="cors-universal-access",
                title="CORS Allows Universal Access",
                description="CORS Access-Control-Allow-Origin is set to '*', allowing any origin.",
                passed=True,
                severity=Severity.LOW,
                score_modifier=-5,
                data={"origin": acao},
                recommendation="Restrict CORS to specific trusted origins if the content is sensitive.",
            )

        return Finding(
            name="cors-restricted",
            title="CORS Properly Restricted",
            description=f"CORS is restricted to: {acao}",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
            data={"origin": acao},
        )

    def _check_referrer_policy(self, ctx: ScanContext) -> Finding:
        """Check Referrer-Policy header."""
        policy = ctx.response_headers.get("Referrer-Policy", "")

        if not policy:
            return Finding(
                name="referrer-policy-not-implemented",
                title="Referrer-Policy Not Set",
                description="Referrer-Policy header is not implemented. Browser will use default behavior.",
                passed=True,
                severity=Severity.LOW,
                score_modifier=0,
                recommendation="Set Referrer-Policy to 'strict-origin-when-cross-origin' or 'no-referrer'.",
            )

        good = {"no-referrer", "same-origin", "strict-origin", "strict-origin-when-cross-origin"}
        bad = {"unsafe-url", "origin", "origin-when-cross-origin"}

        policy_value = policy.strip().lower()

        if policy_value in good:
            return Finding(
                name="referrer-policy-private",
                title="Referrer-Policy Properly Configured",
                description=f"Referrer-Policy set to '{policy_value}' — referrer information is restricted.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=5,
                data={"policy": policy_value},
            )

        if policy_value in bad:
            return Finding(
                name="referrer-policy-unsafe",
                title="Referrer-Policy Set Unsafely",
                description=f"Referrer-Policy '{policy_value}' may leak sensitive URL information.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-5,
                data={"policy": policy_value},
                recommendation="Use 'strict-origin-when-cross-origin' or 'no-referrer' instead.",
            )

        return Finding(
            name="referrer-policy-invalid",
            title="Referrer-Policy Invalid",
            description=f"Referrer-Policy value '{policy_value}' is not recognized.",
            passed=False,
            severity=Severity.LOW,
            score_modifier=-5,
            recommendation="Set a valid Referrer-Policy value.",
        )

    def _check_permissions_policy(self, ctx: ScanContext) -> Finding:
        """Check Permissions-Policy (formerly Feature-Policy) header."""
        pp = ctx.response_headers.get(
            "Permissions-Policy",
            ctx.response_headers.get("Feature-Policy", ""),
        )

        if not pp:
            return Finding(
                name="permissions-policy-not-implemented",
                title="Permissions-Policy Not Set",
                description="Permissions-Policy header is not configured. Browser features are not restricted.",
                passed=False,
                severity=Severity.LOW,
                score_modifier=-5,
                recommendation="Set Permissions-Policy to restrict camera, microphone, geolocation, etc.",
            )

        return Finding(
            name="permissions-policy-implemented",
            title="Permissions-Policy Configured",
            description="Permissions-Policy header restricts browser feature access.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=5,
            data={"policy": pp[:256]},
        )

    def _check_x_frame_options(self, ctx: ScanContext) -> Finding:
        """Check X-Frame-Options header."""
        xfo = ctx.response_headers.get("X-Frame-Options", "")

        # Also check CSP frame-ancestors
        csp = ctx.response_headers.get("Content-Security-Policy", "")
        has_frame_ancestors = "frame-ancestors" in csp.lower()

        if has_frame_ancestors:
            return Finding(
                name="x-frame-options-via-csp",
                title="Clickjacking Protection via CSP",
                description="Clickjacking is prevented via CSP frame-ancestors directive.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=5,
            )

        if not xfo:
            return Finding(
                name="x-frame-options-not-implemented",
                title="X-Frame-Options Not Set",
                description="X-Frame-Options header is missing. Site may be vulnerable to clickjacking.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-15,
                recommendation="Add 'X-Frame-Options: DENY' or 'SAMEORIGIN', or use CSP frame-ancestors.",
            )

        xfo_lower = xfo.strip().lower()
        if xfo_lower in ("deny", "sameorigin"):
            return Finding(
                name="x-frame-options-set",
                title="X-Frame-Options Configured",
                description=f"X-Frame-Options set to '{xfo.strip()}'.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
                data={"value": xfo.strip()},
            )

        return Finding(
            name="x-frame-options-invalid",
            title="X-Frame-Options Invalid",
            description=f"X-Frame-Options value '{xfo.strip()}' is not valid.",
            passed=False,
            severity=Severity.MEDIUM,
            score_modifier=-15,
            recommendation="Set X-Frame-Options to DENY or SAMEORIGIN.",
        )

    def _check_x_content_type_options(self, ctx: ScanContext) -> Finding:
        """Check X-Content-Type-Options header."""
        xcto = ctx.response_headers.get("X-Content-Type-Options", "")

        if xcto.strip().lower() == "nosniff":
            return Finding(
                name="x-content-type-options-nosniff",
                title="X-Content-Type-Options Set",
                description="X-Content-Type-Options is set to 'nosniff', preventing MIME type sniffing.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )

        return Finding(
            name="x-content-type-options-not-implemented",
            title="X-Content-Type-Options Not Set",
            description="X-Content-Type-Options header is missing. Browser may perform MIME sniffing.",
            passed=False,
            severity=Severity.LOW,
            score_modifier=-5,
            recommendation="Add 'X-Content-Type-Options: nosniff' header.",
        )

    def _check_x_xss_protection(self, ctx: ScanContext) -> Finding:
        """Check X-XSS-Protection header (deprecated but informational)."""
        xxp = ctx.response_headers.get("X-XSS-Protection", "")

        # This header is deprecated — we just note its presence/absence
        return Finding(
            name="x-xss-protection-present" if xxp else "x-xss-protection-absent",
            title="X-XSS-Protection (Deprecated)",
            description=f"X-XSS-Protection is set to '{xxp.strip()}'."
            if xxp
            else "X-XSS-Protection header not set. This header is deprecated in modern browsers.",
            passed=True,  # No penalty either way — deprecated
            severity=Severity.INFO,
            score_modifier=0,
            data={"value": xxp.strip()} if xxp else {},
        )

    def _check_redirect_security(self, ctx: ScanContext) -> Finding:
        """Check that redirect chain goes to HTTPS."""
        chain = ctx.redirect_chain

        if not chain:
            return Finding(
                name="redirect-not-needed",
                title="No Redirects",
                description="No redirect chain — site was accessed directly.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
            )

        final_is_https = urlparse(ctx.final_url or ctx.url).scheme == "https"
        all_https = all(urlparse(u).scheme == "https" for u in chain)

        if final_is_https and all_https:
            return Finding(
                name="redirect-to-https",
                title="Secure Redirect Chain",
                description="All redirects use HTTPS.",
                passed=True,
                severity=Severity.INFO,
                score_modifier=0,
                data={"chain": chain},
            )

        if final_is_https and not all_https:
            return Finding(
                name="redirect-mixed",
                title="Mixed HTTP/HTTPS Redirect",
                description="Redirect chain contains HTTP hops before reaching HTTPS.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-10,
                data={"chain": chain},
                recommendation="Ensure all redirects go directly to HTTPS without HTTP intermediaries.",
            )

        return Finding(
            name="redirect-not-to-https",
            title="Redirect Does Not End at HTTPS",
            description="The final destination is not HTTPS.",
            passed=False,
            severity=Severity.HIGH,
            score_modifier=-20,
            data={"chain": chain, "final_url": ctx.final_url},
            recommendation="Configure redirects to end at an HTTPS URL.",
        )
