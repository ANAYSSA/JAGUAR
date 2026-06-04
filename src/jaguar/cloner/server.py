"""
Local development server for serving cloned websites.

Allows the user to view the downloaded site locally via HTTP
instead of file:// protocol to avoid CORS and module issues.

Features:
- Smart entry-point detection (auto-redirect to main page)
- Proper MIME types for web fonts and manifests
"""

from __future__ import annotations

import logging
import mimetypes
import os
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer
from typing import Any

logger = logging.getLogger("jaguar.cloner.server")

# Register additional MIME types
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/otf", ".otf")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")


def detect_entry_point(directory: str) -> str | None:
    """Detect the main entry page of a cloned website."""
    root = Path(directory)

    # Check root index.html
    if (root / "index.html").exists():
        return None  # Default serving works fine

    # Search for index.html in subdirectories (prefer shallowest)
    indexes = sorted(root.rglob("index.html"), key=lambda p: len(p.parts))
    if indexes:
        rel = indexes[0].relative_to(root)
        return str(rel).replace("\\", "/")

    # Search for any HTML file
    html_files = sorted(root.rglob("*.html"), key=lambda p: len(p.parts))
    if html_files:
        rel = html_files[0].relative_to(root)
        return str(rel).replace("\\", "/")

    return None


def ensure_root_index(directory: str) -> str | None:
    """Create a root index.html redirect if one doesn't exist."""
    root = Path(directory)
    root_index = root / "index.html"

    if root_index.exists():
        return None

    entry = detect_entry_point(directory)
    if entry:
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="0; url={entry}">
    <title>Redirecting...</title>
</head>
<body>
    <p>Redirecting to <a href="{entry}">{entry}</a></p>
</body>
</html>
"""
        root_index.write_text(html, encoding="utf-8")
        logger.info("Created redirect: index.html → %s", entry)
        return entry

    return None


class SPARequestHandler(SimpleHTTPRequestHandler):
    """Custom handler for SPA routing and asset error logging."""

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        if code == 404:
            # Check if this looks like an asset vs a route
            path = self.path.split('?')[0].split('#')[0]
            ext = Path(path).suffix.lower()

            # Known asset extensions that should naturally 404 instead of serving index.html
            asset_exts = {'.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf', '.json', '.webmanifest'}

            if ext in asset_exts:
                # Log actual broken asset!
                # We use print here with ANSI colors because the standard logger might not hit the console nicely if rich isn't wrapping it.
                print(f"\033[91m[404] Broken Asset:\033[0m {self.path}")
                super().send_error(code, message, explain)
                return

            # Otherwise, assume it's a client-side SPA route and return index.html
            index_path = Path(self.directory) / "index.html"
            if index_path.exists():
                try:
                    with open(index_path, 'rb') as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception:
                    pass

            print(f"\033[91m[404] Route Not Found:\033[0m {self.path}")

        super().send_error(code, message, explain)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress standard HTTP logs unless it's an error to keep console clean during SPA testing
        pass


class CloneServer:
    """Simple HTTP server to serve cloned websites locally."""

    def __init__(self, directory: str, port: int = 8080):
        self.directory = os.path.abspath(directory)
        self.port = port
        self.server: TCPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> str:
        """Start the server in a background thread."""
        if not os.path.exists(self.directory):
            raise FileNotFoundError(f"Directory {self.directory} does not exist.")

        # Ensure directory is actually a valid clone (must contain some HTML)
        root = Path(self.directory)
        if not (root / "index.html").exists() and not list(root.rglob("*.html")):
            raise ValueError(f"Refusing to serve {self.directory}: Not a valid JAGUAR clone (no HTML files found). This prevents accidental exposure of user directories.")

        # Ensure entry point exists
        entry = ensure_root_index(self.directory)
        if entry:
            logger.info("Auto-detected entry point: %s", entry)

        # Ensure we change to the right directory for the handler
        original_dir = os.getcwd()
        os.chdir(self.directory)

        try:
            handler = SPARequestHandler
            # allow_reuse_address prevents "Address already in use" errors
            TCPServer.allow_reuse_address = True

            # Find an available port if default is taken
            max_attempts = 10
            for i in range(max_attempts):
                try:
                    self.server = TCPServer(("", self.port + i), handler)
                    self.port = self.port + i
                    break
                except OSError as e:
                    if "Address already in use" in str(e) and i < max_attempts - 1:
                        continue
                    raise

            assert self.server is not None

            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()

            url = f"http://localhost:{self.port}"
            logger.info("Serving %s at %s", self.directory, url)
            return url

        finally:
            os.chdir(original_dir)

    def stop(self) -> None:
        """Stop the background server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        logger.info("Clone server stopped.")
