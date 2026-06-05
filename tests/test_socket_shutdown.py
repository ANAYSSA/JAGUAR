import socket
import tempfile
from pathlib import Path
import pytest
from jaguar.cloner.server import CloneServer

def test_socket_shutdown_and_multiple_stops() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create a valid index.html to allow server startup
        (root / "index.html").write_text("<html><body>Test</body></html>", encoding="utf-8")

        # Find a free port
        s = socket.socket()
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.close()

        server = CloneServer(tmpdir, port=port)
        url = server.start()
        assert url.startswith("http://localhost:")

        # Ensure server thread is running
        assert server.thread is not None
        assert server.thread.is_alive()

        # Stop the server
        server.stop()

        # Verify stopped status
        assert server.server is None
        assert server.thread is None

        # Verify calling stop() again doesn't crash or raise errors (excludes double shutdown/close)
        server.stop()
        server.stop()

        # Verify we cannot start it again if stopped (excludes serve_forever on destroyed server)
        with pytest.raises(RuntimeError):
            server.start()
