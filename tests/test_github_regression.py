import pytest
import os
import shutil
from pathlib import Path
from jaguar.cloner.engine import ClonerEngine

@pytest.mark.asyncio
async def test_github_regression_clone() -> None:
    """Verify GitHub clones perfectly without 500 errors and preserves language."""
    target = "https://github.com/"
    clone_dir = Path("d:/JAGUAR/tests/test_clones")
    
    if clone_dir.exists():
        shutil.rmtree(clone_dir)
        
    engine = ClonerEngine(
        output_dir=str(clone_dir),
        max_depth=1,
        max_pages=2,
        concurrency=1,
        render_spa=True
    )
    
    path = await engine.clone(target)
    assert os.path.exists(path)
    
    report_path = Path(path) / "CLONE_REPORT.md"
    assert report_path.exists()
    
    content = report_path.read_text("utf-8")
    assert "Overall Health" in content
    
    # Check language preservation in report
    assert "Final Site Language" in content
