"""
Local development server for serving cloned websites.

Allows the user to view the downloaded site locally via HTTP
instead of file:// protocol to avoid CORS and module issues.
"""

from __future__ import annotations

import logging
import os
import threading
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

logger = logging.getLogger("jaguar.cloner.server")


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

        # Ensure we change to the right directory for the handler
        original_dir = os.getcwd()
        os.chdir(self.directory)

        try:
            handler = SimpleHTTPRequestHandler
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
