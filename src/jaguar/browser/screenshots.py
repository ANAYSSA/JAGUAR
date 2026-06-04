"""
Screenshot gallery capture for JAGUAR.

Requirement #5: Generate desktop, tablet, and mobile screenshots
during scans. Screenshots are stored locally and referenced in reports.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from jaguar.browser.manager import VIEWPORTS, BrowserManager
from jaguar.core.models import Screenshot, ViewportType

logger = logging.getLogger("jaguar.screenshots")


async def capture_screenshot_gallery(
    browser: BrowserManager,
    url: str,
    *,
    output_dir: str | None = None,
) -> list[Screenshot]:
    """
    Capture screenshots at desktop, tablet, and mobile viewports.

    Returns a list of Screenshot objects with paths to the saved files.
    """
    if output_dir is None:
        output_dir = os.path.join("jaguar-reports", "screenshots")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    screenshots: list[Screenshot] = []
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # Sanitize hostname for filename
    from jaguar.utils.url import extract_hostname

    hostname = extract_hostname(url).replace(".", "_")

    viewport_types = [
        (ViewportType.DESKTOP, "desktop"),
        (ViewportType.TABLET, "tablet"),
        (ViewportType.MOBILE, "mobile"),
    ]

    for vp_type, vp_name in viewport_types:
        try:
            page = await browser.new_page(viewport=vp_name)

            try:
                await browser.navigate_and_wait(page, url)

                # Wait a bit for any animations
                await page.wait_for_timeout(1000)

                vp = VIEWPORTS[vp_name]
                filename = f"{hostname}_{vp_name}_{timestamp}.png"
                filepath = os.path.join(output_dir, filename)

                await browser.capture_screenshot(page, filepath, full_page=True)

                screenshots.append(
                    Screenshot(
                        viewport=vp_type,
                        width=vp["width"],
                        height=vp["height"],
                        path=os.path.abspath(filepath),
                    )
                )

                logger.info("Captured %s screenshot for %s", vp_name, url)

            finally:
                await page.close()

        except Exception as e:
            logger.warning("Failed to capture %s screenshot: %s", vp_name, e)

    return screenshots
