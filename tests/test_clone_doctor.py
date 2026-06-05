import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from click.testing import CliRunner
import pytest

from jaguar.cli import cli
from jaguar.cloner.validator import CloneReport, CategoryHealth


def test_clone_doctor_static_only() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "index.html").write_text("<html></html>", encoding="utf-8")
        
        # Mock CloneValidator to return a report with static failures
        mock_report = CloneReport()
        mock_report.html.total = 1
        mock_report.html.resolved = 1
        mock_report.css = CategoryHealth(total=2, resolved=1, missing=["theme/styles.css"])
        mock_report.js = CategoryHealth(total=1, resolved=0, missing=["js/main.js"])
        
        mock_validator = MagicMock()
        mock_validator._run_static_checks.return_value = mock_report
        
        with patch("jaguar.cloner.validator.CloneValidator", return_value=mock_validator), \
             patch("jaguar.cloner.server.detect_entry_point", return_value="index.html"):
            
            runner = CliRunner()
            result = runner.invoke(cli, ["clone-doctor", tmpdir])
            
            assert result.exit_code == 0
            assert "Running Static Analysis" in result.output
            assert "CSS Failure" in result.output
            assert "JS Failure" in result.output
            assert "theme/styles.css" in result.output
            assert "js/main.js" in result.output


def test_clone_doctor_deep_dynamic() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "index.html").write_text("<html></html>", encoding="utf-8")
        
        # Mock CloneValidator to return a report with rendering errors
        mock_report = CloneReport()
        mock_report.html.total = 1
        mock_report.html.resolved = 1
        mock_report.has_rendering_errors = True
        mock_report.rendering_error_logs = [
            "[Console] CORS error: Access to XMLHttpRequest at 'http://api.com' blocked.",
            "[Console] Refused to apply style from 'http://site.com/style.php' because its MIME type ('text/plain') is not supported.",
            "[Console] Failed to load resource: the server responded with a status of 404 (Not Found) (http://site.com/assets/font.woff2)",
            "[Console] Failed to load resource: the server responded with a status of 404 (Not Found) (http://site.com/service.php?ajax=1)",
            "[Console] Uncaught TypeError: Cannot read properties of undefined (reading 'foo')",
            "[Console] Failed to load resource: net::ERR_CONTENT_DECODING_FAILED (http://site.com/compressed.js)"
        ]
        
        mock_validator = MagicMock()
        mock_validator._run_static_checks.return_value = mock_report
        mock_validator._run_playwright_validation = AsyncMock(return_value=mock_report)
        
        with patch("jaguar.cloner.validator.CloneValidator", return_value=mock_validator), \
             patch("jaguar.cloner.server.detect_entry_point", return_value="index.html"):
            
            runner = CliRunner()
            result = runner.invoke(cli, ["clone-doctor", tmpdir, "--deep"])
            
            assert result.exit_code == 0
            assert "Running Deep Dynamic Browser Analysis" in result.output
            
            # Check for the expected categorized outputs from doctor's sorting logic
            assert "Category: cors failures" in result.output
            assert "Category: MIME mismatch" in result.output
            assert "Category: font failures" in result.output
            assert "Category: ajax failures" in result.output
            assert "Category: js exceptions" in result.output
            assert "Category: decoding failures" in result.output
