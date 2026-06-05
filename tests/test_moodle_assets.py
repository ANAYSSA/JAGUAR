import pytest
from pathlib import Path
from unittest.mock import MagicMock
from jaguar.cloner.engine import ClonerEngine
from jaguar.cloner.rebuilder import classify_file

def test_moodle_assets_classification_and_unquoting(tmp_path: Path) -> None:
    # 1. Test that unquoting works in engine's _url_to_local_path
    engine = ClonerEngine(output_dir=str(tmp_path))
    url = "https://lms.astanait.edu.kz/pluginfile.php/1/core_admin/logo/0x200/1759344969/Astana%20IT%20University%20%284%29.png"
    local_path = engine._url_to_local_path(url, tmp_path, is_html=False)
    
    # Path should contain space and brackets, not %20 or %28
    assert "Astana IT University (4).png" in str(local_path)

    # 2. Test classify_file behaves correctly for styles.php or theme.php
    styles_php = tmp_path / "styles.php"
    styles_php.write_text("body { color: red; }", encoding="utf-8")
    assert classify_file(styles_php) == "css"
