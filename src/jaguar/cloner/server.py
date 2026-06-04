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
    """Detect the main entry page of a cloned website by size."""
    root = Path(directory)

    # Search for known primary entry files recursively
    candidates = []
    for name in ["index.html", "home.html", "default.html", "main.html", "app.html"]:
        candidates.extend(root.rglob(name))
        
    if candidates:
        # Pick the one with the largest file size
        best = max(candidates, key=lambda p: p.stat().st_size)
        return str(best.relative_to(root)).replace("\\", "/")

    # Fallback to ANY HTML file
    html_files = list(root.rglob("*.html"))
    if html_files:
        best = max(html_files, key=lambda p: p.stat().st_size)
        return str(best.relative_to(root)).replace("\\", "/")

    return None


def ensure_root_index(directory: str) -> str | None:
    """Create a root index.html redirect if one doesn't exist."""
    root = Path(directory)
    root_index = root / "index.html"

    entry = detect_entry_point(directory)
    
    if not entry and not root_index.exists():
        raise ValueError(f"No valid HTML entry point found in {directory}. The directory might be empty or not a cloned website.")
        
    if root_index.exists() and not entry:
        return None
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

            print(f"\033[91m[404] Route Not Found (Offline Placeholder served):\033[0m {self.path}")
            
            # Serve Generated Offline Placeholder
            offline_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Offline Placeholder - JAGUAR</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; text-align: center; padding: 100px 20px; color: #333; }}
        h1 {{ color: #e53e3e; }}
        .box {{ max-width: 600px; margin: 0 auto; background: #f7fafc; padding: 40px; border-radius: 8px; border: 1px solid #e2e8f0; }}
        code {{ background: #edf2f7; padding: 2px 6px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="box">
        <h1>Offline Route Triggered</h1>
        <p>The clone navigated to a route that was not fully downloaded or requires a backend server:</p>
        <p><code>{self.path}</code></p>
        <p>This offline placeholder prevents the browser from crashing into a raw 404 error.</p>
        <a href="/">Return to Home</a>
    </div>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(offline_html.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(offline_html.encode('utf-8'))
            return

        super().send_error(code, message, explain)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress standard HTTP logs unless it's an error to keep console clean during SPA testing
        pass

    def guess_type(self, path: str) -> str:
        """Override MIME type guessing using .meta.json and Sec-Fetch-Dest."""
        try:
            import os, json
            meta_path = path + ".meta.json"
            if os.path.exists(meta_path):
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                if meta.get("Content-Type"):
                    return meta["Content-Type"].split(";")[0]
        except Exception:
            pass
            
        dest = self.headers.get("Sec-Fetch-Dest")
        if dest == "style":
            return "text/css"
        if dest == "script":
            return "application/javascript"
        if dest == "font":
            return "font/woff2"
            
        return super().guess_type(path)

    def end_headers(self) -> None:
        try:
            import os, json
            path = self.translate_path(self.path)
            meta_path = path + ".meta.json"
            if os.path.exists(meta_path):
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                if meta.get("Content-Encoding"):
                    self.send_header("Content-Encoding", meta["Content-Encoding"])
                if meta.get("Cache-Control"):
                    self.send_header("Cache-Control", meta["Cache-Control"])
        except Exception:
            pass
        super().end_headers()


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
