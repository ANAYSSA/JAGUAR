import json
import tempfile
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jaguar.cloner.engine import ClonerEngine


@pytest.mark.asyncio
async def test_github_language_determination_and_sidecar() -> None:
    # We want to test language determination without doing actual HTTP requests.
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create an engine with language override
        engine = ClonerEngine(
            output_dir=tmpdir,
            max_depth=1,
            max_pages=1,
            concurrency=1,
            locale_override="es-ES"
        )
        
        # Test determination logic
        engine._determine_locale()
        assert engine.site_language == "es-ES"
        assert engine.selected_language == "es-ES"
        assert engine.language_source == "CLI Override"
        
        # Check accept header generation
        hdr = engine._get_accept_language_header()
        assert "es-ES" in hdr
        assert "es" in hdr

        # Mock the HTTP client and clone flow to test sidecar writing
        engine.base_url = "https://github.com"
        
        mock_response = MagicMock()
        mock_response.headers = {"Content-Language": "es"}
        
        mock_http = MagicMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        
        async def mock_pw_impl(target_dir):
            try:
                engine._queue.get_nowait()
                engine._queue.task_done()
            except Exception:
                pass

        # We patch HttpClient and other post clone phases to avoid real operations
        with patch("jaguar.cloner.engine.HttpClient") as mock_http_cls, \
             patch.object(engine, "_page_worker", side_effect=mock_pw_impl) as mock_pw, \
             patch.object(engine, "_asset_worker", AsyncMock()) as mock_aw, \
             patch.object(engine, "_post_clone", AsyncMock()) as mock_pc:
             
            # Setup context manager for HttpClient
            mock_http_instance = AsyncMock()
            mock_http_instance.__aenter__.return_value = mock_http
            mock_http_cls.return_value = mock_http_instance
            
            # Run the clone
            await engine.clone("https://github.com")
            
            # Verify that .jaguar-locale.json has been written properly under cloned site dir
            target_dir = Path(tmpdir) / "github.com"
            locale_json_path = target_dir / ".jaguar-locale.json"
            
            assert locale_json_path.exists()
            locale_data = json.loads(locale_json_path.read_text(encoding="utf-8"))
            assert locale_data["locale"] == "es-ES"
            assert locale_data["language"] == "es"
            assert "accept_language" in locale_data


@pytest.mark.asyncio
async def test_github_language_fallback_to_os() -> None:
    # Test fallback to OS/default locale when "auto" is selected
    engine = ClonerEngine(
        locale_override="auto"
    )
    
    with patch.object(engine, "_get_windows_locale", return_value="fr-FR"):
        engine._determine_locale()
        assert engine.site_language == "fr-FR"
        assert engine.selected_language == "fr-FR"
        assert engine.language_source == "OS Locale (Auto)"


@pytest.mark.asyncio
async def test_github_language_en() -> None:
    from jaguar.cloner.validator import CloneValidator
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_dir = Path(tmpdir)
        
        # 1. Mismatch case: requested=en, html lang=de
        lang_report = {
            "requested_language": "en-US",
            "final_language": "en-US",
            "detected_html_lang": "de"
        }
        (clone_dir / "language_report.json").write_text(json.dumps(lang_report), encoding="utf-8")
        (clone_dir / "index.html").write_text('<html lang="de"><head></head><body>German</body></html>', encoding="utf-8")
        
        validator = CloneValidator(clone_dir)
        with patch.object(validator, "_run_playwright_validation", AsyncMock(side_effect=lambda r, b, bm: r)), \
             patch.object(validator, "_run_static_checks") as mock_static:
             
             from jaguar.cloner.validator import CloneReport
             report = CloneReport()
             report.html.total = 1
             report.html.resolved = 1
             mock_static.return_value = report
             
             res = await validator.validate("https://github.com")
             assert res.language_mismatch is True
             assert res.overall_health == 0.0

        # 2. Matching case: requested=en, html lang=en
        lang_report = {
            "requested_language": "en-US",
            "final_language": "en-US",
            "detected_html_lang": "en"
        }
        (clone_dir / "language_report.json").write_text(json.dumps(lang_report), encoding="utf-8")
        (clone_dir / "index.html").write_text('<html lang="en"><head></head><body>English</body></html>', encoding="utf-8")
        
        with patch.object(validator, "_run_playwright_validation", AsyncMock(side_effect=lambda r, b, bm: r)), \
             patch.object(validator, "_run_static_checks") as mock_static:
             
             report = CloneReport()
             report.html.total = 1
             report.html.resolved = 1
             mock_static.return_value = report
             
             res = await validator.validate("https://github.com")
             assert res.language_mismatch is False
             assert res.overall_health > 0.0


@pytest.mark.asyncio
async def test_github_language_ru() -> None:
    from jaguar.cloner.validator import CloneValidator
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_dir = Path(tmpdir)
        
        # requested=ru, html lang=ru
        lang_report = {
            "requested_language": "ru-RU",
            "final_language": "ru-RU",
            "detected_html_lang": "ru"
        }
        (clone_dir / "language_report.json").write_text(json.dumps(lang_report), encoding="utf-8")
        (clone_dir / "index.html").write_text('<html lang="ru"><head></head><body>Russian</body></html>', encoding="utf-8")
        
        validator = CloneValidator(clone_dir)
        with patch.object(validator, "_run_playwright_validation", AsyncMock(side_effect=lambda r, b, bm: r)), \
             patch.object(validator, "_run_static_checks") as mock_static:
             
             from jaguar.cloner.validator import CloneReport
             report = CloneReport()
             report.html.total = 1
             report.html.resolved = 1
             mock_static.return_value = report
             
             res = await validator.validate("https://github.com")
             assert res.language_mismatch is False
             assert res.overall_health > 0.0
