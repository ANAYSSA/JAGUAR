"""
Playwright browser lifecycle manager for JAGUAR.

Manages a shared Chromium browser instance used by analyzers
that need DOM access (accessibility, UX, AI design, AI detect).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("jaguar.browser")

# Viewport presets
VIEWPORTS = {
    "desktop": {"width": 1920, "height": 1080},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 375, "height": 812},
}


class BrowserManager:
    """
    Manages a Playwright browser instance.

    Provides page creation with configurable viewports,
    screenshot capture, and JavaScript injection.
    """

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._playwright: Any = None
        self._browser: Any = None
        self._started = False

    async def start(self) -> None:
        """Launch the browser."""
        if self._started:
            return

        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            self._started = True
            logger.info("Browser launched (headless=%s)", self._headless)

        except ImportError as e:
            raise ImportError(
                "Playwright is required for browser-dependent features. "
                "Install with: pip install jaguar[browser] && playwright install chromium"
            ) from e

    async def close(self) -> None:
        """Close the browser and cleanup."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._started = False
        logger.info("Browser closed")

    async def new_page(
        self,
        viewport: str = "desktop",
        *,
        user_agent: str | None = None,
        locale: str | None = None,
    ) -> Any:
        """
        Create a new browser page with the specified viewport.

        Args:
            viewport: One of 'desktop', 'tablet', 'mobile'
            user_agent: Optional custom user agent
            locale: Optional locale to set for the context

        Returns:
            Playwright Page object
        """
        if not self._started:
            await self.start()

        assert self._browser is not None

        vp = VIEWPORTS.get(viewport, VIEWPORTS["desktop"])

        context_options: dict[str, Any] = {
            "viewport": vp,
            "ignore_https_errors": True,
        }
        if user_agent:
            context_options["user_agent"] = user_agent
        if locale:
            context_options["locale"] = locale
            lang_code = locale.split("-")[0]
            if lang_code != locale:
                accept_lang = f"{locale},{lang_code};q=0.9,en;q=0.8"
            else:
                accept_lang = f"{locale},en;q=0.9"
            context_options["extra_http_headers"] = {"Accept-Language": accept_lang}

        context = await self._browser.new_context(**context_options)
        page = await context.new_page()

        return page

    async def navigate_and_wait(
        self,
        page: Any,
        url: str,
        *,
        wait_until: str = "networkidle",
        timeout: int = 30000,
    ) -> Any:
        """Navigate to a URL and wait for the page to load. Returns the Response object."""
        try:
            return await page.goto(url, wait_until=wait_until, timeout=timeout)
        except Exception as e:
            logger.warning(
                "Navigation to %s with wait_until=%s failed: %s. Retrying with 'load'.",
                url,
                wait_until,
                e,
            )
            try:
                return await page.goto(url, wait_until="load", timeout=timeout)
            except Exception as e2:
                logger.error("Navigation to %s failed: %s", url, e2)
                raise

    async def capture_screenshot(
        self,
        page: Any,
        path: str,
        *,
        full_page: bool = True,
    ) -> str:
        """Capture a screenshot and save it to the given path."""
        await page.screenshot(path=path, full_page=full_page)
        logger.debug("Screenshot saved to %s", path)
        return path

    async def inject_script(self, page: Any, script: str) -> Any:
        """Inject and evaluate JavaScript on the page."""
        return await page.evaluate(script)

    async def get_page_content(self, page: Any) -> str:
        """Get the full HTML content of the page after JS rendering."""
        return await page.content()  # type: ignore

    @property
    def is_started(self) -> bool:
        return self._started
