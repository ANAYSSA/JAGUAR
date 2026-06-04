"""
URL normalization and validation utilities for JAGUAR.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """
    Normalize a URL for consistent processing.

    - Adds https:// if no scheme is present
    - Lowercases the hostname
    - Removes trailing slashes from path (unless path is just '/')
    - Removes default ports (80 for http, 443 for https)
    - Removes fragment identifiers
    """
    url = url.strip()

    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = f"https://{url}"

    parsed = urlparse(url)

    # Lowercase hostname
    hostname = (parsed.hostname or "").lower()

    # Remove default ports
    port = parsed.port
    if (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80):
        port = None

    netloc = hostname
    if port:
        netloc = f"{hostname}:{port}"

    # Clean path
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            path,
            parsed.params,
            parsed.query,
            "",  # drop fragment
        )
    )


def extract_hostname(url: str) -> str:
    """Extract the hostname from a URL."""
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    return parsed.hostname or ""


def extract_base_url(url: str) -> str:
    """Extract the base URL (scheme + host) without path."""
    parsed = urlparse(normalize_url(url))
    return f"{parsed.scheme}://{parsed.netloc}"


def is_same_origin(url1: str, url2: str) -> bool:
    """Check if two URLs have the same origin (scheme + host + port)."""
    p1 = urlparse(normalize_url(url1))
    p2 = urlparse(normalize_url(url2))
    return (p1.scheme, p1.netloc) == (p2.scheme, p2.netloc)


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid HTTP(S) URL."""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return bool(
            parsed.scheme in ("http", "https") and parsed.hostname and "." in parsed.hostname
        )
    except Exception:
        return False


def make_absolute(relative_url: str, base_url: str) -> str:
    """Convert a relative URL to absolute given a base URL."""
    if relative_url.startswith(("http://", "https://", "//")):
        return relative_url

    base = urlparse(base_url)

    if relative_url.startswith("/"):
        return f"{base.scheme}://{base.netloc}{relative_url}"

    # Relative to current path
    base_path = base.path
    if "/" in base_path:
        base_path = base_path.rsplit("/", 1)[0]

    return f"{base.scheme}://{base.netloc}{base_path}/{relative_url}"


def get_domain_parts(hostname: str) -> dict[str, str]:
    """
    Break a hostname into its component parts.

    Returns dict with keys: subdomain, domain, tld, registered_domain
    """
    parts = hostname.lower().split(".")

    if len(parts) >= 3:
        return {
            "subdomain": ".".join(parts[:-2]),
            "domain": parts[-2],
            "tld": parts[-1],
            "registered_domain": ".".join(parts[-2:]),
        }
    elif len(parts) == 2:
        return {
            "subdomain": "",
            "domain": parts[0],
            "tld": parts[1],
            "registered_domain": hostname,
        }
    else:
        return {
            "subdomain": "",
            "domain": hostname,
            "tld": "",
            "registered_domain": hostname,
        }
