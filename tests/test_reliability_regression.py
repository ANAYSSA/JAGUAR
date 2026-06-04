import json
import tempfile
from pathlib import Path

import pytest

from jaguar.cloner.rebuilder import classify_file
from jaguar.cloner.validator import CloneReport


def test_dynamic_file_classification() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # 1. CSS via metadata
        css_file = root / "styles-dynamic.php"
        css_file.write_text("body { background: #000; }", encoding="utf-8")
        meta_file = root / "styles-dynamic.php.meta.json"
        meta_file.write_text(json.dumps({"Content-Type": "text/css; charset=UTF-8"}), encoding="utf-8")

        assert classify_file(css_file) == "css"

        # 2. JS via metadata
        js_file = root / "script-dynamic.php"
        js_file.write_text("console.log('test');", encoding="utf-8")
        js_meta = root / "script-dynamic.php.meta.json"
        js_meta.write_text(json.dumps({"Content-Type": "application/javascript"}), encoding="utf-8")

        assert classify_file(js_file) == "js"

        # 3. HTML by extension
        html_file = root / "index.php"
        html_file.write_text("<html><body>Hello</body></html>", encoding="utf-8")
        assert classify_file(html_file) == "html"


def test_double_encoded_url_handling() -> None:
    from jaguar.cloner.link_rewriter import LinkRewriter

    rewriter = LinkRewriter("https://example.com")
    url = "https://example.com/assets%252Fimage.png" # double encoded
    rewritten = rewriter._rewrite_url(url, "https://example.com/index.html", is_asset=True)
    assert "assets/image.png" in rewritten or "../assets/image.png" in rewritten


def test_strict_health_score_calculation() -> None:
    report = CloneReport()
    report.html.total = 1
    report.html.resolved = 1

    # 1. Missing CSS should cap the score at 80%
    report.css.total = 5
    report.css.resolved = 4
    report.css.missing.append("styles.css")

    assert report.overall_health <= 80.0

    # 2. Console errors should cap at 90% and subtract further
    report2 = CloneReport()
    report2.html.total = 1
    report2.html.resolved = 1
    report2.has_rendering_errors = True
    report2.rendering_error_logs.append("[Console] Failed to load resource: styles.css")

    assert report2.overall_health <= 90.0
    assert report2.overall_health < 100.0


@pytest.mark.asyncio
async def test_suffix_matching_spa_routing() -> None:
    import socket

    from jaguar.cloner.server import CloneServer

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index_file = root / "index.html"
        index_file.write_text("<html><body>SPA Root</body></html>", encoding="utf-8")

        # Create an asset in the static folder
        static_dir = root / "static" / "js"
        static_dir.mkdir(parents=True, exist_ok=True)
        js_file = static_dir / "main.js"
        js_file.write_text("console.log('main');", encoding="utf-8")

        # Find available port
        s = socket.socket()
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.close()

        server = CloneServer(tmpdir, port=port)
        url = server.start()

        # Try fetching the asset directly and via nested SPA route
        import aiohttp
        async with aiohttp.ClientSession() as session:
            # 1. Fetch index.html
            async with session.get(url + "/") as r:
                assert r.status == 200

            # 2. Fetch asset directly
            async with session.get(url + "/static/js/main.js") as r:
                assert r.status == 200
                assert "console.log('main');" in await r.text()

            # 3. Fetch nested asset route /user/settings/static/js/main.js
            async with session.get(url + "/user/settings/static/js/main.js") as r:
                assert r.status == 200
                assert "console.log('main');" in await r.text()

            # 4. Fetch non-existent route (should serve SPA index.html)
            async with session.get(url + "/some/spa/route") as r:
                assert r.status == 200
                assert "SPA Root" in await r.text()

        server.stop()
