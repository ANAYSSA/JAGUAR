"""
Shared async HTTP client for JAGUAR.

Provides a managed aiohttp session with:
- Configurable timeouts and retries with exponential backoff
- Response caching to avoid duplicate fetches across analyzers
- TLS certificate information capture
- Cookie jar management
- User-Agent management
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import ssl
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp
import certifi

logger = logging.getLogger("jaguar.http")

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; JAGUAR/1.0; +https://github.com/anayssa/jaguar)"

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=15)
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.5


@dataclass
class CachedResponse:
    """Cached HTTP response data."""

    status: int
    headers: dict[str, str]
    body: str
    url: str
    final_url: str
    redirect_history: list[str]
    cookies: list[dict[str, Any]]
    tls_info: dict[str, Any]
    content_type: str
    elapsed_ms: float


@dataclass
class HttpClientConfig:
    """Configuration for the HTTP client."""

    timeout: aiohttp.ClientTimeout = field(default_factory=lambda: DEFAULT_TIMEOUT)
    max_retries: int = MAX_RETRIES
    user_agent: str = DEFAULT_USER_AGENT
    verify_ssl: bool = True
    follow_redirects: bool = True
    max_redirects: int = 10
    headers: dict[str, str] = field(default_factory=dict)


class HttpClient:
    """
    Managed async HTTP client with caching and TLS capture.

    Usage:
        async with HttpClient() as client:
            response = await client.get("https://example.com")
    """

    def __init__(self, config: HttpClientConfig | None = None) -> None:
        self._config = config or HttpClientConfig()
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, CachedResponse] = {}
        self._ssl_context: ssl.SSLContext | None = None

    async def __aenter__(self) -> HttpClient:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def start(self) -> None:
        """Initialize the aiohttp session."""
        if self._session is not None:
            return

        self._ssl_context = ssl.create_default_context(cafile=certifi.where())
        if not self._config.verify_ssl:
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(
            ssl=self._ssl_context,
            limit=20,
            limit_per_host=5,
        )

        default_headers = {
            "User-Agent": self._config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }
        default_headers.update(self._config.headers)

        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=self._config.timeout,
            headers=default_headers,
            cookie_jar=aiohttp.CookieJar(),
        )

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

    def _cache_key(self, url: str, method: str = "GET") -> str:
        """Generate a cache key for a request."""
        return hashlib.sha256(f"{method}:{url}".encode()).hexdigest()[:16]

    async def get(
        self,
        url: str,
        *,
        use_cache: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> CachedResponse:
        """
        Perform a GET request with retries and caching.

        Returns a CachedResponse with all captured data.
        """
        cache_key = self._cache_key(url)
        if use_cache and cache_key in self._cache:
            logger.debug("Cache hit for %s", url)
            return self._cache[cache_key]

        response = await self._request("GET", url, extra_headers=extra_headers)

        if use_cache:
            self._cache[cache_key] = response

        return response

    async def head(self, url: str) -> CachedResponse:
        """Perform a HEAD request."""
        return await self._request("HEAD", url)

    async def fetch_resource(
        self,
        url: str,
        *,
        use_cache: bool = True,
    ) -> CachedResponse:
        """Fetch a sub-resource (JS, CSS, etc.) — same as get but semantically distinct."""
        return await self.get(url, use_cache=use_cache)

    async def check_url_exists(self, url: str) -> bool:
        """Check if a URL responds with a 2xx status."""
        try:
            resp = await self.head(url)
            return 200 <= resp.status < 300
        except Exception:
            return False

    async def _request(
        self,
        method: str,
        url: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> CachedResponse:
        """Execute an HTTP request with retry logic."""
        if not self._session:
            await self.start()

        assert self._session is not None

        last_error: Exception | None = None

        headers = dict(extra_headers) if extra_headers else {}
        if getattr(self, "enterprise_mode", False) and "User-Agent" not in headers:
            headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        for attempt in range(self._config.max_retries):
            try:
                start = time.monotonic()
                async with self._session.request(
                    method,
                    url,
                    allow_redirects=self._config.follow_redirects,
                    max_redirects=self._config.max_redirects,
                    headers=headers,
                    ssl=self._ssl_context,  # type: ignore
                ) as resp:
                    body = ""
                    if method != "HEAD":
                        body = await resp.text(errors="replace")

                    elapsed = (time.monotonic() - start) * 1000

                    # Capture redirect chain
                    redirect_chain = [str(h.url) for h in resp.history]

                    # Capture cookies
                    cookies = []
                    for cookie in self._session.cookie_jar:
                        secure_val = cookie.get("secure", "")
                        is_secure = secure_val is True or (isinstance(secure_val, str) and "secure" in secure_val.lower())

                        httponly_val = cookie.get("httponly", "")
                        is_httponly = httponly_val is True or (isinstance(httponly_val, str) and httponly_val != "")

                        cookies.append(
                            {
                                "name": cookie.key,
                                "value": cookie.value,
                                "domain": cookie.get("domain", ""),
                                "path": cookie.get("path", "/"),
                                "secure": is_secure,
                                "httponly": is_httponly,
                                "samesite": cookie.get("samesite", ""),
                            }
                        )

                    # Capture TLS info
                    tls_info = await self._extract_tls_info(resp)

                    # Flatten headers (take first value for duplicate keys)
                    headers = {k: v for k, v in resp.headers.items()}

                    return CachedResponse(
                        status=resp.status,
                        headers=headers,
                        body=body,
                        url=url,
                        final_url=str(resp.url),
                        redirect_history=redirect_chain,
                        cookies=cookies,
                        tls_info=tls_info,
                        content_type=resp.content_type or "",
                        elapsed_ms=elapsed,
                    )

            except (TimeoutError, aiohttp.ClientError, OSError) as e:
                last_error = e
                if attempt < self._config.max_retries - 1:
                    delay = RETRY_BACKOFF_BASE**attempt
                    logger.warning(
                        "Request to %s failed (attempt %d/%d): %s. Retrying in %.1fs",
                        url,
                        attempt + 1,
                        self._config.max_retries,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Request to %s failed after %d attempts: %s",
                        url,
                        self._config.max_retries,
                        e,
                    )

        raise ConnectionError(
            f"Failed to fetch {url} after {self._config.max_retries} attempts: {last_error}"
        )

    @staticmethod
    async def _extract_tls_info(
        response: aiohttp.ClientResponse,
    ) -> dict[str, Any]:
        """Extract TLS/SSL information from the response connection."""
        tls_info: dict[str, Any] = {}
        try:
            transport = response.connection
            if transport is None:
                return tls_info

            sock = transport.transport
            if sock is None:
                return tls_info

            ssl_object = sock.get_extra_info("ssl_object")
            if ssl_object is None:
                return tls_info

            tls_info["protocol"] = ssl_object.version()
            tls_info["cipher"] = ssl_object.cipher()

            cert = ssl_object.getpeercert()
            if cert:
                tls_info["subject"] = dict(x[0] for x in cert.get("subject", ()))
                tls_info["issuer"] = dict(x[0] for x in cert.get("issuer", ()))
                tls_info["not_before"] = cert.get("notBefore", "")
                tls_info["not_after"] = cert.get("notAfter", "")
                tls_info["serial_number"] = cert.get("serialNumber", "")
                tls_info["san"] = [entry[1] for entry in cert.get("subjectAltName", ())]
        except Exception as e:
            logger.debug("Could not extract TLS info: %s", e)

        return tls_info

    @property
    def cache_stats(self) -> dict[str, int]:
        """Return cache statistics."""
        return {"entries": len(self._cache)}

    def clear_cache(self) -> None:
        """Clear the response cache."""
        self._cache.clear()
