"""
Single Page Application (SPA) renderer for JAGUAR Cloner.

Uses Playwright to render JavaScript-heavy sites (React, Next.js, Vue)
into static HTML before saving, ensuring cloned sites actually work offline.
Requirement #8: SPA Cloning Support.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

logger = logging.getLogger("jaguar.cloner.spa")


class SPARenderer:
    """Renders JS-heavy pages into static HTML."""

    def __init__(self, browser_manager: Any):
        """Initialize with a BrowserManager instance."""
        self.browser = browser_manager

    async def render_to_static_html(self, url: str) -> str:
        """
        Navigate to URL, wait for JS framework to render, and return static HTML.
        """
        if not self.browser.is_started:
            await self.browser.start()

        page = None
        try:
            page = await self.browser.new_page()

            # Navigate and wait for network to be idle (JS loaded)
            await self.browser.navigate_and_wait(page, url, wait_until="networkidle")

            # Additional wait for frameworks that hydrate late
            # Check for common SPA root elements
            await self._wait_for_framework(page)

            # Remove scripts to prevent re-execution when viewed offline
            await self._strip_executable_scripts(page)

            # Return fully rendered static HTML
            html = await self.browser.get_page_content(page)
            return html  # type: ignore

        except Exception as e:
            logger.error("SPA rendering failed for %s: %s", url, e)
            raise
        finally:
            if page:
                await page.close()

    async def _wait_for_framework(self, page: Any) -> None:
        """Wait for common JS frameworks to finish initial rendering."""
        script = """
        () => {
            return new Promise((resolve) => {
                // Quick resolution if page already has substantial content
                if (document.body.innerHTML.length > 5000) {
                    resolve();
                    return;
                }

                // Wait up to 3 seconds for framework hydration
                let checks = 0;
                const interval = setInterval(() => {
                    const hasReact = !!document.querySelector('[data-reactroot], #__next > div, #root > div');
                    const hasVue = !!document.querySelector('[data-v-], [data-vue-app]');
                    const hasAngular = !!document.querySelector('[ng-version]');

                    if (hasReact || hasVue || hasAngular || checks > 30) {
                        clearInterval(interval);
                        resolve();
                    }
                    checks++;
                }, 100);
            });
        }
        """
        with contextlib.suppress(Exception):
            await self.browser.inject_script(page, script)

    async def _strip_executable_scripts(self, page: Any) -> None:
        """Remove or disable script tags so the static clone doesn't try to re-hydrate/fetch."""
        script = """
        () => {
            const scripts = document.querySelectorAll('script');
            scripts.forEach(s => {
                // Remove application scripts to prevent hydration errors offline
                if (s.src && (s.src.includes('_next') || s.src.includes('nuxt') ||
                              s.src.includes('react') || s.src.includes('vue'))) {
                    s.remove();
                } else if (!s.src) {
                    // Disable inline scripts by changing type
                    s.type = 'text/plain';
                }
            });

            // Remove Next.js / Nuxt data script tags
            document.querySelectorAll('#__NEXT_DATA__, #__NUXT_DATA__').forEach(e => e.remove());
        }
        """
        with contextlib.suppress(Exception):
            await self.browser.inject_script(page, script)
