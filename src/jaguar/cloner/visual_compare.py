"""
Visual comparison engine for JAGUAR Cloner.

Captures screenshots of the original website and the local clone,
then compares them pixel-by-pixel to produce a visual accuracy score.

Requires Playwright for browser-based screenshot capture.
"""

from __future__ import annotations

import logging
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("jaguar.cloner.visual_compare")


@dataclass
class VisualComparisonResult:
    """Result of a visual comparison between original and clone."""

    accuracy: float = 0.0
    original_screenshot: str = ""
    clone_screenshot: str = ""
    diff_pixels: int = 0
    total_pixels: int = 0
    console_errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        s = (
            f"Visual Accuracy: {self.accuracy:.1f}%\n"
            f"Total Pixels: {self.total_pixels}\n"
            f"Different Pixels: {self.diff_pixels}"
        )
        if self.console_errors:
            s += f"\nBrowser Console Errors: {len(self.console_errors)}"
        return s


class VisualCompare:
    """Compares original website with its clone visually."""

    def __init__(self, clone_dir: Path):
        self.clone_dir = clone_dir

    async def compare(
        self, original_url: str, local_port: int = 8090
    ) -> VisualComparisonResult:
        """
        Capture screenshots of original and clone, compare them.

        1. Screenshot original URL via Playwright
        2. Serve clone on a temp port
        3. Screenshot localhost clone via Playwright
        4. Pixel-diff the two images
        """
        result = VisualComparisonResult()

        try:
            from jaguar.browser.manager import BrowserManager
        except ImportError:
            logger.error("Playwright not available for visual comparison")
            result.accuracy = -1.0
            return result

        # Screenshots directory
        screenshots_dir = self.clone_dir / ".jaguar-screenshots"
        screenshots_dir.mkdir(exist_ok=True)

        original_path = screenshots_dir / "original.png"
        clone_path = screenshots_dir / "clone.png"

        browser = BrowserManager(headless=True)

        try:
            await browser.start()

            # 1. Screenshot original
            logger.info("Capturing screenshot of original: %s", original_url)
            page = await browser.new_page()
            try:
                await browser.navigate_and_wait(page, original_url)
                await page.screenshot(path=str(original_path), full_page=True)
            finally:
                await page.close()

            # 2. Start temp server and screenshot clone
            import http.server
            import socketserver
            import threading

            _clone_dir = str(self.clone_dir)

            class Handler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *args: object, **kwargs: object) -> None:
                    super().__init__(*args, directory=_clone_dir, **kwargs)  # type: ignore[arg-type]

                def log_message(self, format: str, *args: object) -> None:
                    pass  # Suppress logs

            socketserver.ThreadingTCPServer.allow_reuse_address = True

            server = socketserver.ThreadingTCPServer(("127.0.0.1", local_port), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                logger.info("Capturing screenshot of clone on port %d", local_port)
                page = await browser.new_page()

                from playwright.async_api import ConsoleMessage, Error, Request
                
                def handle_console(msg: ConsoleMessage) -> None:
                    if msg.type in ("error", "warning") and "Failed to load resource" in msg.text:
                        result.console_errors.append(msg.text)
                    elif msg.type == "error":
                        result.console_errors.append(f"Console error: {msg.text}")

                def handle_pageerror(err: Error) -> None:
                    result.console_errors.append(f"JS Exception: {err}")

                def handle_requestfailed(req: Request) -> None:
                    if req.failure:
                        result.console_errors.append(f"Request failed: {req.url} ({req.failure})")

                page.on("console", handle_console)
                page.on("pageerror", handle_pageerror)
                page.on("requestfailed", handle_requestfailed)

                try:
                    await browser.navigate_and_wait(
                        page, f"http://localhost:{local_port}"
                    )
                    await page.screenshot(path=str(clone_path), full_page=True)
                finally:
                    await page.close()
            finally:
                server.shutdown()
                server.server_close()

            # 3. Compare screenshots
            if original_path.exists() and clone_path.exists():
                result = self._compare_images(
                    original_path.read_bytes(),
                    clone_path.read_bytes(),
                )
                result.original_screenshot = str(original_path)
                result.clone_screenshot = str(clone_path)

        except Exception as e:
            logger.error("Visual comparison failed: %s", e)
            result.accuracy = -1.0
        finally:
            await browser.close()

        return result

    def _compare_images(
        self, img_a_bytes: bytes, img_b_bytes: bytes
    ) -> VisualComparisonResult:
        """Compare two PNG images pixel-by-pixel."""
        result = VisualComparisonResult()

        try:
            pixels_a = self._decode_png_pixels(img_a_bytes)
            pixels_b = self._decode_png_pixels(img_b_bytes)

            if pixels_a is None or pixels_b is None:
                result.accuracy = 0.0
                return result

            # Use the smaller dimensions for comparison
            min_len = min(len(pixels_a), len(pixels_b))
            if min_len == 0:
                result.accuracy = 0.0
                return result

            total_pixels = min_len // 3  # RGB
            diff_pixels = 0
            total_diff = 0.0

            for i in range(0, min_len - 2, 3):
                r_diff = abs(pixels_a[i] - pixels_b[i])
                g_diff = abs(pixels_a[i + 1] - pixels_b[i + 1])
                b_diff = abs(pixels_a[i + 2] - pixels_b[i + 2])
                pixel_diff = (r_diff + g_diff + b_diff) / (255 * 3)
                total_diff += pixel_diff
                if pixel_diff > 0.1:  # Threshold for "different"
                    diff_pixels += 1

            # Account for size difference as missing pixels
            size_diff = abs(len(pixels_a) - len(pixels_b)) // 3
            total_pixels += size_diff
            diff_pixels += size_diff

            accuracy = max(0.0, (1.0 - total_diff / max(total_pixels, 1)) * 100)

            result.accuracy = round(accuracy, 1)
            result.diff_pixels = diff_pixels
            result.total_pixels = total_pixels

        except Exception as e:
            logger.error("Image comparison failed: %s", e)
            result.accuracy = 0.0

        return result

    def _decode_png_pixels(self, png_bytes: bytes) -> bytes | None:
        """Decode PNG to raw RGB pixel data (basic decoder)."""
        try:
            # Validate PNG signature
            if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
                return None

            # Parse chunks to find IHDR and IDAT
            pos = 8
            width = height = 0
            idat_data = b""

            while pos < len(png_bytes):
                length = struct.unpack(">I", png_bytes[pos : pos + 4])[0]
                chunk_type = png_bytes[pos + 4 : pos + 8]
                chunk_data = png_bytes[pos + 8 : pos + 8 + length]

                if chunk_type == b"IHDR":
                    width = struct.unpack(">I", chunk_data[0:4])[0]
                    height = struct.unpack(">I", chunk_data[4:8])[0]
                elif chunk_type == b"IDAT":
                    idat_data += chunk_data
                elif chunk_type == b"IEND":
                    break

                pos += 12 + length  # 4 length + 4 type + data + 4 crc

            if width == 0 or height == 0:
                return None

            # Decompress
            raw = zlib.decompress(idat_data)

            # Unfilter (simplified — only handles filter type 0: None)
            # For a basic accuracy metric this is sufficient
            stride = width * 4 + 1  # RGBA + filter byte
            pixels = bytearray()
            for y in range(min(height, len(raw) // stride)):
                row_start = y * stride + 1  # Skip filter byte
                for x in range(width):
                    px = row_start + x * 4
                    if px + 2 < len(raw):
                        pixels.extend(raw[px : px + 3])  # RGB only

            return bytes(pixels)

        except Exception:
            return None
