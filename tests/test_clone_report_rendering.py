from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from jaguar.cli import cli
from jaguar.cloner.validator import CategoryHealth, CloneReport


@patch("jaguar.cli.click.secho")
@patch("jaguar.cli.click.echo")
@patch("jaguar.cli.ClonerEngine")
def test_clone_report_rendering(
    mock_engine_cls: MagicMock, mock_echo: MagicMock, mock_secho: MagicMock
) -> None:
    # Mock the ClonerEngine to avoid actual network requests
    mock_engine = MagicMock()
    mock_engine_cls.return_value = mock_engine

    # Setup mock return values
    mock_engine.clone = AsyncMock(return_value="/tmp/dummy")

    # Create a dummy report
    report = CloneReport()
    report.css = CategoryHealth(total=10, resolved=10)
    report.js = CategoryHealth(total=5, resolved=5)
    report.images = CategoryHealth(total=20, resolved=18, missing=["img1.png"])
    report.fonts = CategoryHealth(total=2, resolved=2)
    report.svg = CategoryHealth(total=0, resolved=0)
    report.media = CategoryHealth(total=0, resolved=0)

    mock_engine.clone_report = report
    mock_engine.visual_result = None

    runner = CliRunner()

    # We call the CLI without --serve so it doesn't block, just prints
    result = runner.invoke(cli, ["clone", "http://example.com"])

    assert result.exit_code == 0
    # No AttributeError should have been raised
