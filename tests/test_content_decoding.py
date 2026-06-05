import gzip
import json
import socket
import tempfile
from pathlib import Path
import pytest
import aiohttp
from jaguar.cloner.server import CloneServer

@pytest.mark.asyncio
async def test_content_decoding_on_the_fly() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "index.html").write_text("<html><body>Test</body></html>", encoding="utf-8")

        # Create a gzip-compressed CSS file
        original_css = "body { color: blue; }"
        compressed_css = gzip.compress(original_css.encode("utf-8"))
        
        css_path = root / "compressed.css"
        css_path.write_bytes(compressed_css)

        # Write meta JSON sidecar with Content-Encoding
        meta = {
            "Content-Type": "text/css",
            "Content-Encoding": "gzip",
        }
        (root / "compressed.css.meta.json").write_text(json.dumps(meta), encoding="utf-8")

        # Find a free port
        s = socket.socket()
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.close()

        server = CloneServer(tmpdir, port=port)
        url = server.start()

        # Fetch CSS and verify it is decompressed and does NOT have Content-Encoding header
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}/compressed.css") as resp:
                assert resp.status == 200
                assert resp.headers.get("Content-Type") == "text/css"
                
                # Header MUST be absent/stripped because the payload is decoded (unpacked)
                assert resp.headers.get("Content-Encoding") is None
                
                text = await resp.text()
                assert text == original_css

        server.stop()
