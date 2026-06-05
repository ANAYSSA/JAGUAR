import json
import socket
import tempfile
from pathlib import Path
import pytest
import aiohttp
from jaguar.cloner.server import CloneServer

@pytest.mark.asyncio
async def test_language_preservation_injection() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "index.html").write_text('<html lang="de"><head><title>Test</title></head><body>Hello</body></html>', encoding="utf-8")

        # Write .jaguar-locale.json sidecar with Spanish locale
        locale_data = {
            "locale": "es-ES",
            "language": "es"
        }
        (root / ".jaguar-locale.json").write_text(json.dumps(locale_data), encoding="utf-8")

        # Find a free port
        s = socket.socket()
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.close()

        server = CloneServer(tmpdir, port=port)
        url = server.start()

        # Fetch index.html and verify:
        # 1. html lang is replaced with "es"
        # 2. navigator.language override script is injected
        # 3. Cookies are set in response
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}/index.html") as resp:
                assert resp.status == 200
                
                # Check cookies
                cookies = resp.cookies
                assert cookies.get("locale").value == "es-ES"
                assert cookies.get("lang").value == "es"
                
                text = await resp.text()
                assert 'lang="es"' in text
                assert 'Object.defineProperty(navigator' in text
                assert 'es-ES' in text

        server.stop()
