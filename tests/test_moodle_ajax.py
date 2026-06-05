import hashlib
import json
import socket
import tempfile
from pathlib import Path
import pytest
import aiohttp
from jaguar.cloner.server import CloneServer

@pytest.mark.asyncio
async def test_moodle_ajax_cache_serving() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "index.html").write_text("<html><body>Test</body></html>", encoding="utf-8")

        # Set up a mock AJAX cache entry
        ajax_cache_dir = root / ".jaguar-ajax-cache"
        ajax_cache_dir.mkdir(parents=True, exist_ok=True)

        method = "POST"
        path = "/lib/ajax/service.php"
        query = "sesskey=123"
        post_data = '{"action": "get_data"}'
        
        cache_key_src = f"{path}?{query}\n{method}\n{post_data}"
        cache_hash = hashlib.sha256(cache_key_src.encode("utf-8")).hexdigest()

        meta = {
            "url": f"https://example.com{path}?{query}",
            "method": method,
            "post_data": post_data,
            "content_type": "application/json",
            "status": 200,
        }
        body_content = '{"status": "success", "data": "offline_mock"}'

        (ajax_cache_dir / f"{cache_hash}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (ajax_cache_dir / f"{cache_hash}.body").write_text(body_content, encoding="utf-8")

        # Find a free port
        s = socket.socket()
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.close()

        server = CloneServer(tmpdir, port=port)
        url = server.start()

        # Send POST request to serve and verify mock AJAX is returned
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{url}{path}?{query}", data=post_data) as resp:
                assert resp.status == 200
                assert resp.headers.get("Content-Type") == "application/json"
                text = await resp.text()
                assert "offline_mock" in text

        server.stop()
