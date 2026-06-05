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


def _is_jaguar_redirect(path: Path) -> bool:
    """Check if an HTML file is a JAGUAR-generated redirect stub."""
    try:
        content = path.read_text("utf-8", errors="replace")
        return 'http-equiv="refresh"' in content and len(content) < 500
    except Exception:
        return False


def _entry_score(path: Path, root: Path) -> tuple[int, int]:
    """Score an entry point candidate. Higher is better.
    Returns (depth_score, size) where depth_score favors shallower files."""
    rel = path.relative_to(root)
    depth = len(rel.parts)
    # Shallower files score higher (invert depth); size is tiebreaker
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return (-depth, size)


def detect_entry_point(directory: str) -> str | None:
    """Detect the main entry page of a cloned website.

    Priority:
    1. Root index.html if it's a real page (not a JAGUAR redirect stub)
    2. Shallowest index.html / index.php / home.html that is a real page
    3. Any HTML/PHP file, shallowest + largest wins
    """
    root = Path(directory)

    # Priority 1: root index.html if real
    root_index = root / "index.html"
    if root_index.exists() and not _is_jaguar_redirect(root_index):
        return "index.html"

    # Priority 2: search for known entry filenames (include .php for Moodle/WordPress)
    entry_names = ["index.html", "index.php", "home.html", "default.html", "main.html", "app.html"]
    candidates: list[Path] = []
    for name in entry_names:
        for p in root.rglob(name):
            if not _is_jaguar_redirect(p):
                candidates.append(p)

    if candidates:
        best = max(candidates, key=lambda p: _entry_score(p, root))
        return str(best.relative_to(root)).replace("\\", "/")

    # Priority 3: any HTML or PHP file
    all_pages = list(root.rglob("*.html")) + list(root.rglob("*.php"))
    all_pages = [p for p in all_pages if not _is_jaguar_redirect(p)]
    if all_pages:
        best = max(all_pages, key=lambda p: _entry_score(p, root))
        return str(best.relative_to(root)).replace("\\", "/")

    return None


def ensure_root_index(directory: str) -> str | None:
    """Create a root index.html redirect if one doesn't exist or is a stale redirect."""
    root = Path(directory)
    root_index = root / "index.html"

    entry = detect_entry_point(directory)

    if not entry and not root_index.exists():
        raise ValueError(f"No valid HTML entry point found in {directory}. The directory might be empty or not a cloned website.")

    if not entry:
        return None

    # If entry IS the root index.html, no redirect needed
    if entry == "index.html":
        return entry

    # If root index.html is a real page (not a redirect), don't overwrite it
    if root_index.exists() and not _is_jaguar_redirect(root_index):
        return entry

    # Create/update redirect stub at root index.html pointing to actual entry
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


def decompress_data(data: bytes, encoding: str) -> bytes:
    encoding = encoding.strip().lower()
    if encoding == "gzip" or data.startswith(b"\x1f\x8b"):
        import gzip
        try:
            return gzip.decompress(data)
        except Exception:
            pass
    if encoding == "deflate" or data.startswith(b"\x78\x01") or data.startswith(b"\x78\x9c") or data.startswith(b"\x78\xda"):
        import zlib
        try:
            return zlib.decompress(data)
        except Exception:
            try:
                return zlib.decompress(data, -15)
            except Exception:
                pass
    if encoding == "br":
        try:
            import brotli  # type: ignore[import-untyped] # pyright: ignore[reportMissingImports]
            return brotli.decompress(data)  # type: ignore[no-any-return]
        except Exception:
            try:
                import brotlicffi as brotli  # type: ignore[import-not-found] # pyright: ignore[reportMissingImports]
                return brotli.decompress(data)  # type: ignore[no-any-return]
            except Exception:
                pass
    return data


class SPARequestHandler(SimpleHTTPRequestHandler):
    """Custom handler for SPA routing, asset error logging, decompression, locale preservation, and AJAX caching."""
    protocol_version = "HTTP/1.0"

    def handle(self) -> None:
        self.close_connection = True
        super().handle()

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_POST(self) -> None:
        """Handle POST requests, serving them from AJAX cache if matched."""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = ""
        if content_length > 0:
            try:
                post_data = self.rfile.read(content_length).decode('utf-8', errors='ignore')
            except Exception:
                pass

        if self._serve_from_ajax_cache("POST", post_data):
            return

        self.send_error(404, f"POST route not in offline cache: {self.path}")

    def _serve_from_ajax_cache(self, method: str, post_data: str) -> bool:
        """Search in .jaguar-ajax-cache for a matching request and serve it."""
        import hashlib
        import json
        from pathlib import Path
        from urllib.parse import urlparse

        ajax_cache_dir = Path(self.directory) / ".jaguar-ajax-cache"
        if not ajax_cache_dir.exists():
            return False

        parsed_url = urlparse(self.path)
        cache_key_src = f"{parsed_url.path}?{parsed_url.query}\n{method.upper()}\n{post_data}"
        cache_hash = hashlib.sha256(cache_key_src.encode("utf-8")).hexdigest()

        meta_file = ajax_cache_dir / f"{cache_hash}.meta.json"
        body_file = ajax_cache_dir / f"{cache_hash}.body"

        if meta_file.exists() and body_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                body_bytes = body_file.read_bytes()
                self.send_response(meta.get("status", 200))
                self.send_header("Content-Type", meta.get("content_type", "application/json"))
                self.send_header("Content-Length", str(len(body_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
                self.send_header("Access-Control-Allow-Headers", "*")
                self.end_headers()
                self.wfile.write(body_bytes)
                logger.debug(f"AJAX cache hit: {method} {self.path}")
                return True
            except Exception as e:
                logger.warning("Failed to serve AJAX cache: %s", e)

        # Fallback: ignore query string/post data, match path only
        try:
            for p in ajax_cache_dir.glob("*.meta.json"):
                try:
                    meta = json.loads(p.read_text(encoding="utf-8"))
                    if meta.get("method") == method.upper():
                        cached_parsed = urlparse(meta.get("url", ""))
                        if cached_parsed.path == parsed_url.path:
                            body_path = p.with_suffix(".body")
                            if body_path.exists():
                                body_bytes = body_path.read_bytes()
                                self.send_response(meta.get("status", 200))
                                self.send_header("Content-Type", meta.get("content_type", "application/json"))
                                self.send_header("Content-Length", str(len(body_bytes)))
                                self.send_header("Access-Control-Allow-Origin", "*")
                                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
                                self.send_header("Access-Control-Allow-Headers", "*")
                                self.end_headers()
                                self.wfile.write(body_bytes)
                                logger.debug(f"AJAX cache path fallback hit: {method} {self.path}")
                                return True
                except Exception:
                    pass
        except Exception:
            pass

        return False

    def send_head(self) -> Any:
        """Override send_head to support decompression, language preservation, and SPA resolution."""
        # 1. First check GET AJAX cache
        if self._serve_from_ajax_cache("GET", ""):
            return None

        path = self.translate_path(self.path)
        import re

        # 2. Suffix matching if the path does not exist directly
        if not os.path.exists(path):
            clean_path = self.path.split('?')[0].split('#')[0]
            ext = Path(clean_path).suffix.lower()
            asset_exts = {
                '.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2',
                '.ttf', '.json', '.webmanifest', '.ico', '.map', '.mp4', '.mp3', '.ogg',
                '.wav', '.webm', '.xml'
            }

            parts = [p for p in clean_path.split("/") if p]
            suffix_found = False
            for i in range(1, len(parts)):
                suffix_path = "/".join(parts[i:])
                resolved_local = Path(self.directory) / suffix_path
                if resolved_local.exists() and resolved_local.is_file():
                    self.path = "/" + suffix_path
                    path = self.translate_path(self.path)
                    suffix_found = True
                    break

            if not suffix_found:
                if ext in asset_exts:
                    print(f"\033[91m[404] Broken Asset:\033[0m {self.path}")
                    self.send_error(404, f"Asset not found: {self.path}")
                    return None

                # Fallback to SPA root index
                index_path = Path(self.directory) / "index.html"
                if index_path.exists():
                    self.path = "/index.html"
                    path = self.translate_path(self.path)
                else:
                    print(f"\033[91m[404] Route Not Found (Offline Placeholder served):\033[0m {self.path}")
                    self.send_error(404)
                    return None

        # 3. Serving file (decompress on the fly, inject locale, headers)
        if os.path.exists(path) and os.path.isfile(path):
            content_type = self.guess_type(path)
            content_encoding = ""
            cache_control = ""

            try:
                import json
                meta_path = path + ".meta.json"
                if os.path.exists(meta_path):
                    with open(meta_path) as f:
                        meta = json.load(f)
                    content_encoding = meta.get("Content-Encoding", "").strip().lower()
                    cache_control = meta.get("Cache-Control", "")
            except Exception:
                pass

            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                self.send_error(404, "File not found")
                return None

            # Sniff compression if not specified in metadata
            is_compressed = False
            if content_encoding in ("gzip", "deflate", "br"):
                is_compressed = True
            elif data.startswith(b"\x1f\x8b"):
                content_encoding = "gzip"
                is_compressed = True
            elif data.startswith(b"\x78\x01") or data.startswith(b"\x78\x9c") or data.startswith(b"\x78\xda"):
                content_encoding = "deflate"
                is_compressed = True

            # Decompress if needed
            if is_compressed:
                decompressed = decompress_data(data, content_encoding)
                if decompressed != data:
                    data = decompressed
                    content_encoding = ""

            # Inject locale/language if HTML file
            if content_type == "text/html":
                try:
                    locale_json = Path(self.directory) / ".jaguar-locale.json"
                    if locale_json.exists():
                        import json
                        locale_meta = json.loads(locale_json.read_text(encoding="utf-8"))
                        locale = locale_meta.get("locale", "en-US")
                        language = locale_meta.get("language", "en")
                    else:
                        locale = "en-US"
                        language = "en"

                    html_text = data.decode("utf-8", errors="replace")

                    # Force html lang attribute matching the clone language
                    html_text = re.sub(r'(<html[^>]*\blang=["\'])([^"\']*)(["\'])', rf'\g<1>{language}\3', html_text, flags=re.IGNORECASE)

                    # Inject navigator.language script override
                    script_inject = f"""<script>
(function() {{
    const targetLocale = "{locale}";
    const targetLanguage = "{language}";
    const targetLanguages = ["{locale}", targetLanguage];
    Object.defineProperty(navigator, 'language', {{ get: () => targetLocale, configurable: true }});
    Object.defineProperty(navigator, 'languages', {{ get: () => targetLanguages, configurable: true }});
    document.cookie = "lang=" + targetLanguage + "; path=/";
    document.cookie = "language=" + targetLanguage + "; path=/";
    document.cookie = "locale=" + targetLocale + "; path=/";
    document.cookie = "NEXT_LOCALE=" + targetLocale + "; path=/";
    document.cookie = "GH_LOCALE=" + targetLocale + "; path=/";
}})();
</script>"""
                    if "<head>" in html_text:
                        html_text = html_text.replace("<head>", f"<head>{script_inject}", 1)
                    elif "<HEAD>" in html_text:
                        html_text = html_text.replace("<HEAD>", f"<HEAD>{script_inject}", 1)
                    else:
                        html_text = script_inject + html_text

                    data = html_text.encode("utf-8")
                except Exception as ex:
                    logger.debug("Failed to inject language override: %s", ex)

            import io
            f_out = io.BytesIO(data)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if content_encoding:
                self.send_header("Content-Encoding", content_encoding)
            if cache_control:
                self.send_header("Cache-Control", cache_control)

            # Set cookies for language/locale in response
            try:
                locale_json = Path(self.directory) / ".jaguar-locale.json"
                if locale_json.exists():
                    import json
                    locale_meta = json.loads(locale_json.read_text(encoding="utf-8"))
                    locale = locale_meta.get("locale", "en-US")
                    language = locale_meta.get("language", "en")
                    self.send_header("Set-Cookie", f"lang={language}; Path=/")
                    self.send_header("Set-Cookie", f"language={language}; Path=/")
                    self.send_header("Set-Cookie", f"locale={locale}; Path=/")
                    self.send_header("Set-Cookie", f"NEXT_LOCALE={locale}; Path=/")
                    self.send_header("Set-Cookie", f"GH_LOCALE={locale}; Path=/")
            except Exception:
                pass

            # Enable CORS for AJAX and assets
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()
            return f_out

        return super().send_head()

    def list_directory(self, path: str | os.PathLike[str]) -> Any:
        """Override directory listing to prevent leaking user files. Return offline placeholder instead."""
        print(f"\033[93m[403] Directory Listing Blocked:\033[0m {self.path}")
        offline_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Directory Listing Blocked - JAGUAR</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; text-align: center; padding: 100px 20px; color: #333; }}
        h1 {{ color: #e53e3e; }}
        .box {{ max-width: 600px; margin: 0 auto; background: #f7fafc; padding: 40px; border-radius: 8px; border: 1px solid #e2e8f0; }}
        code {{ background: #edf2f7; padding: 2px 6px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="box">
        <h1>Directory Access Blocked</h1>
        <p>JAGUAR explicitly blocks directory listings to protect local files.</p>
        <p><code>{self.path}</code></p>
        <a href="/">Return to Home</a>
    </div>
</body>
</html>"""
        self.send_response(403)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(offline_html.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(offline_html.encode('utf-8'))
        return None

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def guess_type(self, path: str | os.PathLike[str]) -> str:
        """Override MIME type guessing using .meta.json and Sec-Fetch-Dest."""
        path_str = os.fspath(path)
        try:
            import json
            meta_path = path_str + ".meta.json"
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
                if meta.get("Content-Type"):
                    return str(meta["Content-Type"].split(";")[0])
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
            import json
            import os
            path = self.translate_path(self.path)
            meta_path = path + ".meta.json"
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
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
        self._stopped = False
        self._serving = False
        self._lock = threading.Lock()

    def start(self) -> str:
        """Start the server in a background thread."""
        with self._lock:
            if self.server or self._stopped:
                raise RuntimeError("Server is already running or has been stopped.")

            if not os.path.exists(self.directory):
                raise FileNotFoundError(f"Directory {self.directory} does not exist.")

            # Ensure directory is actually a valid clone
            root = Path(self.directory)
            if not (root / "index.html").exists() and not list(root.rglob("*.html")) and not list(root.rglob("*.php")):
                raise ValueError(f"Refusing to serve {self.directory}: Not a valid JAGUAR clone.")

            entry = ensure_root_index(self.directory)
            if not entry:
                raise ValueError(f"Refusing to serve {self.directory}: Entry point could not be detected.")

            entry_path = os.path.abspath(os.path.join(self.directory, entry))
            if not os.path.exists(entry_path):
                raise FileNotFoundError(f"Refusing to serve {self.directory}: Detected entry point '{entry}' does not exist.")

            common_path = os.path.commonpath([self.directory, entry_path])
            if common_path != self.directory:
                raise PermissionError(f"Refusing to serve {self.directory}: Entry point '{entry}' is outside the clone directory.")

            logger.info("Auto-detected entry point: %s", entry)

            import functools
            handler = functools.partial(SPARequestHandler, directory=self.directory)

            TCPServer.allow_reuse_address = True
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
            self._stopped = False
            self.thread = threading.Thread(target=self._run_server, daemon=True)
            self.thread.start()

            url = f"http://localhost:{self.port}"
            logger.info("Serving %s at %s", self.directory, url)
            return url

    def _run_server(self) -> None:
        """Target for serve_forever thread."""
        with self._lock:
            if not self.server or self._stopped:
                return
            server = self.server
            self._serving = True
        try:
            server.serve_forever()
        finally:
            with self._lock:
                self._serving = False

    def stop(self) -> None:
        """Stop the background server."""
        with self._lock:
            server = self.server
            if self._stopped or not server:
                return
            self._stopped = True

            # 1. shutdown serve_forever loop first, only if serving, using a timeout thread
            if self._serving:
                try:
                    shutdown_thread = threading.Thread(target=server.shutdown, daemon=True)
                    shutdown_thread.start()
                    shutdown_thread.join(timeout=1.0)
                except Exception:
                    pass
            # 2. close socket
            try:
                server.server_close()
            except Exception:
                pass
            self.server = None

            # 3. wait for thread to terminate to ensure no thread runs after close
            if self.thread:
                try:
                    self.thread.join(timeout=1.0)
                except Exception:
                    pass
                self.thread = None
            logger.info("Clone server stopped.")
