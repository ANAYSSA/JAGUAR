"""
Secrets analyzer for JAGUAR.

Detects exposed secrets, API keys, tokens, source maps, and
configuration files in page source code. Patterns inspired by
gitleaks but reimplemented for web page analysis.
"""

from __future__ import annotations

import logging
import re

from jaguar.analyzers.base import BaseAnalyzer
from jaguar.core.models import AnalyzerCategory, Finding, ScanContext, Severity

logger = logging.getLogger("jaguar.analyzers.secrets")

# Secret patterns — regex + description + severity
SECRET_PATTERNS: list[dict] = [  # type: ignore
    {
        "name": "aws-access-key",
        "regex": r"(?:AKIA|ASIA)[0-9A-Z]{16}",
        "desc": "AWS Access Key ID",
        "severity": Severity.CRITICAL,
    },
    {
        "name": "aws-secret-key",
        "regex": r"(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY)\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})",
        "desc": "AWS Secret Access Key",
        "severity": Severity.CRITICAL,
    },
    {
        "name": "google-api-key",
        "regex": r"AIza[0-9A-Za-z_-]{35}",
        "desc": "Google API Key",
        "severity": Severity.HIGH,
    },
    {
        "name": "google-oauth",
        "regex": r"[0-9]+-[0-9A-Za-z_]{32}\.apps\.googleusercontent\.com",
        "desc": "Google OAuth Client ID",
        "severity": Severity.MEDIUM,
    },
    {
        "name": "github-token",
        "regex": r"gh[ps]_[A-Za-z0-9_]{36}",
        "desc": "GitHub Personal Access Token",
        "severity": Severity.CRITICAL,
    },
    {
        "name": "github-oauth",
        "regex": r"gho_[A-Za-z0-9_]{36}",
        "desc": "GitHub OAuth Token",
        "severity": Severity.CRITICAL,
    },
    {
        "name": "gitlab-token",
        "regex": r"glpat-[A-Za-z0-9_-]{20}",
        "desc": "GitLab Personal Access Token",
        "severity": Severity.CRITICAL,
    },
    {
        "name": "stripe-publishable",
        "regex": r"pk_(?:live|test)_[A-Za-z0-9]{24,}",
        "desc": "Stripe Publishable Key",
        "severity": Severity.LOW,
    },
    {
        "name": "stripe-secret",
        "regex": r"sk_(?:live|test)_[A-Za-z0-9]{24,}",
        "desc": "Stripe Secret Key",
        "severity": Severity.CRITICAL,
    },
    {
        "name": "slack-token",
        "regex": r"xox[baprs]-[0-9A-Za-z-]{10,}",
        "desc": "Slack Token",
        "severity": Severity.HIGH,
    },
    {
        "name": "slack-webhook",
        "regex": r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+",
        "desc": "Slack Webhook URL",
        "severity": Severity.HIGH,
    },
    {
        "name": "twilio-api-key",
        "regex": r"SK[0-9a-f]{32}",
        "desc": "Twilio API Key",
        "severity": Severity.HIGH,
    },
    {
        "name": "sendgrid-api-key",
        "regex": r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}",
        "desc": "SendGrid API Key",
        "severity": Severity.HIGH,
    },
    {
        "name": "jwt-token",
        "regex": r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
        "desc": "JSON Web Token",
        "severity": Severity.MEDIUM,
    },
    {
        "name": "private-key",
        "regex": r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----",
        "desc": "Private Key",
        "severity": Severity.CRITICAL,
    },
    {
        "name": "firebase-url",
        "regex": r"[a-z0-9-]+\.firebaseio\.com",
        "desc": "Firebase Database URL",
        "severity": Severity.MEDIUM,
    },
    {
        "name": "firebase-api-key",
        "regex": r"AIza[0-9A-Za-z\\-_]{35}",
        "desc": "Firebase API Key",
        "severity": Severity.MEDIUM,
    },
    {
        "name": "mailgun-api-key",
        "regex": r"key-[0-9a-z]{32}",
        "desc": "Mailgun API Key",
        "severity": Severity.HIGH,
    },
    {
        "name": "heroku-api-key",
        "regex": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "desc": "Potential Heroku API Key",
        "severity": Severity.MEDIUM,
    },
    {
        "name": "generic-password",
        "regex": r"""(?:password|passwd|pwd|secret)\s*[=:]\s*['"][^'"]{8,}['"]""",
        "desc": "Hardcoded Password/Secret",
        "severity": Severity.CRITICAL,
    },
    {
        "name": "generic-api-key",
        "regex": r"""(?:api[_-]?key|apikey|api[_-]?secret)\s*[=:]\s*['"][A-Za-z0-9_-]{16,}['"]""",
        "desc": "Generic API Key",
        "severity": Severity.HIGH,
    },
]

# Sensitive file paths to probe
SENSITIVE_PATHS = [
    ("/.env", "Environment variables file"),
    ("/.git/config", "Git configuration"),
    ("/config.json", "Configuration file"),
    ("/config.yml", "Configuration file"),
    ("/wp-config.php", "WordPress configuration"),
    ("/.htpasswd", "Apache password file"),
    ("/phpinfo.php", "PHP Info page"),
    ("/.DS_Store", "macOS directory metadata"),
    ("/server-status", "Apache server status"),
    ("/debug", "Debug endpoint"),
    ("/.well-known/security.txt", "Security contact file"),
]


class SecretsAnalyzer(BaseAnalyzer):
    """Detects exposed secrets, API keys, and sensitive files."""

    name = "secrets"
    category = AnalyzerCategory.SECRETS
    weight = 1.3

    async def _run_checks(self, context: ScanContext) -> list[Finding]:
        findings: list[Finding] = []

        # Check page source for secrets
        findings.extend(self._scan_source_for_secrets(context.response_body))

        # Check for exposed source maps
        findings.append(self._check_source_maps(context))

        # Check for sensitive file exposure
        findings.extend(await self._check_sensitive_paths(context))

        # Check for exposed API endpoints in JS
        findings.extend(self._check_api_endpoints(context.response_body))

        return findings

    def _scan_source_for_secrets(self, html: str) -> list[Finding]:
        """Scan page source for secret patterns."""
        findings: list[Finding] = []
        found_types: set[str] = set()

        for pattern in SECRET_PATTERNS:
            matches = re.findall(pattern["regex"], html, re.IGNORECASE)
            if matches and pattern["name"] not in found_types:
                found_types.add(pattern["name"])

                # Redact the actual secret value
                redacted = [self._redact(m) if isinstance(m, str) else "***" for m in matches[:3]]

                findings.append(
                    Finding(
                        name=f"exposed-{pattern['name']}",
                        title=f"Exposed {pattern['desc']}",
                        description=f"Found {len(matches)} instance(s) of {pattern['desc']} in page source.",
                        passed=False,
                        severity=pattern["severity"],
                        score_modifier=-20 if pattern["severity"] == Severity.CRITICAL else -10,
                        data={"count": len(matches), "redacted_samples": redacted},
                        recommendation=f"Remove {pattern['desc']} from client-side code. Use environment variables and server-side APIs.",
                    )
                )

        if not found_types:
            findings.append(
                Finding(
                    name="no-secrets-found",
                    title="No Exposed Secrets",
                    description="No API keys, tokens, or secrets detected in page source.",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=0,
                )
            )

        return findings

    def _check_source_maps(self, ctx: ScanContext) -> Finding:
        """Check for exposed source map files."""
        has_sourcemap_header = (
            "SourceMap" in ctx.response_headers or "X-SourceMap" in ctx.response_headers
        )

        # Check for sourceMappingURL in JS resources

        # Check script resources for .map references
        map_refs = [r for r in ctx.page_resources if r.get("url", "").endswith(".map")]

        if has_sourcemap_header or map_refs:
            return Finding(
                name="exposed-source-maps",
                title="Source Maps Exposed",
                description="Source map files are publicly accessible, exposing original source code.",
                passed=False,
                severity=Severity.MEDIUM,
                score_modifier=-10,
                recommendation="Disable source maps in production or restrict access to them.",
            )

        return Finding(
            name="no-source-maps-exposed",
            title="No Exposed Source Maps",
            description="No publicly accessible source maps detected.",
            passed=True,
            severity=Severity.INFO,
            score_modifier=0,
        )

    async def _check_sensitive_paths(self, ctx: ScanContext) -> list[Finding]:
        """Check for exposed sensitive files at common paths."""
        findings: list[Finding] = []
        from jaguar.core.http_client import HttpClient

        try:
            async with HttpClient() as http:
                for path, desc in SENSITIVE_PATHS[:5]:  # Limit to avoid excessive requests
                    url = f"{ctx.base_url}{path}"
                    try:
                        resp = await http.get(url, use_cache=False)
                        if resp.status == 200 and len(resp.body) > 0 and not self._is_soft_404(resp.body):
                                findings.append(
                                    Finding(
                                        name=f"exposed-file-{path.strip('/').replace('/', '-')}",
                                        title=f"Sensitive File Exposed: {path}",
                                        description=f"{desc} is publicly accessible at {path}.",
                                        passed=False,
                                        severity=Severity.HIGH,
                                        score_modifier=-15,
                                        recommendation=f"Restrict access to {path} using server configuration.",
                                    )
                                )
                    except Exception:
                        pass
        except Exception:
            pass

        if not findings:
            findings.append(
                Finding(
                    name="no-sensitive-files",
                    title="No Sensitive Files Exposed",
                    description="Common sensitive file paths are not publicly accessible.",
                    passed=True,
                    severity=Severity.INFO,
                    score_modifier=0,
                )
            )

        return findings

    def _check_api_endpoints(self, html: str) -> list[Finding]:
        """Detect exposed API endpoints in JavaScript."""
        findings: list[Finding] = []

        api_patterns = [
            r'(?:fetch|axios|XMLHttpRequest)\s*\(\s*["\']([^"\']*api[^"\']*)["\']',
            r'(?:baseURL|apiUrl|API_URL|endpoint)\s*[=:]\s*["\']([^"\']+)["\']',
        ]

        endpoints: set[str] = set()
        for pattern in api_patterns:
            for match in re.finditer(pattern, html, re.IGNORECASE):
                endpoint = match.group(1)
                if endpoint.startswith(("http://", "https://", "/")):
                    endpoints.add(endpoint)

        if endpoints:
            findings.append(
                Finding(
                    name="exposed-api-endpoints",
                    title="API Endpoints Discovered",
                    description=f"Found {len(endpoints)} API endpoint(s) in client-side code.",
                    passed=True,  # Not necessarily a vulnerability
                    severity=Severity.INFO,
                    score_modifier=0,
                    data={"endpoints": list(endpoints)[:10]},
                )
            )

        return findings

    @staticmethod
    def _redact(value: str) -> str:
        """Redact a secret value, showing only first/last 3 chars."""
        if len(value) <= 8:
            return "***"
        return f"{value[:3]}...{value[-3:]}"

    @staticmethod
    def _is_soft_404(body: str) -> bool:
        """Detect soft 404 pages (custom error pages that return 200)."""
        indicators = ["page not found", "404", "not found", "does not exist"]
        body_lower = body.lower()[:1000]
        return any(ind in body_lower for ind in indicators)
