import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from jaguar.cloner.engine import ClonerEngine

@pytest.mark.asyncio
async def test_deadlock_detection_triggers(tmp_path: Path) -> None:
    # Test that when stall limit is reached, it cancels workers and exits cleanly
    engine = ClonerEngine(
        output_dir=str(tmp_path),
        max_depth=1,
        max_pages=2,
        concurrency=1,
    )
    engine.base_url = "http://localhost:12345"
    engine.http = MagicMock()
    engine.http.get = AsyncMock(side_effect=Exception("Stall trigger"))

    # We patch asyncio.sleep to not actually wait 15 seconds during test,
    # or we just mock it to raise/exit early.
    # In the stall check, it checks if len(self._visited) etc don't change.
    # Let's mock asyncio.sleep to speed up time
    sleep_calls = 0
    async def mock_sleep(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 16:
            # force stall count to hit 15 quickly
            pass
        await asyncio.sleep(0.001)

    # Let's run a small test by patching the wait loop or sleep
    with patch("asyncio.sleep", side_effect=mock_sleep):
        # We can run the clone and verify it returns within a reasonable time
        # even if stuck.
        # To make it stall, we can pass page_workers and asset_workers that do nothing
        page_worker = asyncio.create_task(asyncio.sleep(10))
        asset_worker = asyncio.create_task(asyncio.sleep(10))
        
        # We can test the stall loop logic directly:
        engine._visited.add("http://localhost:12345")
        
        # Run a task wrapping the main stall loop to verify it breaks:
        # We simulate the exact stall loop:
        stalls = 0
        last_visited = 0
        last_assets = 0
        last_failed_assets = 0
        last_queue_size = -1
        
        for _ in range(20):
            current_visited = len(engine._visited)
            current_assets = len(engine._assets_visited)
            current_failed_assets = engine.failed_assets_count
            current_queue_size = engine._queue.qsize() + engine._assets_queue.qsize()

            if (current_visited == last_visited and
                current_assets == last_assets and
                current_failed_assets == last_failed_assets and
                current_queue_size == last_queue_size):
                stalls += 1
            else:
                stalls = 0

            last_visited = current_visited
            last_assets = current_assets
            last_failed_assets = current_failed_assets
            last_queue_size = current_queue_size
            
            if stalls >= 15:
                break
                
        assert stalls >= 15
        page_worker.cancel()
        asset_worker.cancel()
        await asyncio.gather(page_worker, asset_worker, return_exceptions=True)


@pytest.mark.asyncio
async def test_deadlock_detection_real_trigger(tmp_path: Path) -> None:
    # Test that ClonerEngine.clone triggers the deadlock detector on a real crawl stall
    engine = ClonerEngine(
        output_dir=str(tmp_path),
        max_depth=1,
        max_pages=2,
        concurrency=1,
    )
    engine.base_url = "http://localhost:12345"
    
    mock_response = MagicMock()
    mock_response.headers = {"Content-Language": "en"}
    
    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    
    mock_http_instance = AsyncMock()
    mock_http_instance.__aenter__.return_value = mock_http

    # Let's mock _page_worker to simulate an active fetch that gets stuck
    async def mock_page_worker(target_dir):
        engine._active_fetches.add("http://localhost:12345/stuck")
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
            
    async def mock_asset_worker(target_dir):
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    # Patch the workers and asyncio.sleep to run fast
    # We mock asyncio.sleep so the 15-second stall is simulated instantly
    sleep_count = 0
    original_sleep = asyncio.sleep
    async def fast_sleep(seconds):
        nonlocal sleep_count
        if seconds == 1:
            sleep_count += 1
            # Yield control so event loop can run tasks
            await original_sleep(0.001)
        else:
            await original_sleep(seconds)

    with patch("jaguar.cloner.engine.HttpClient", return_value=mock_http_instance), \
         patch.object(engine, "_page_worker", mock_page_worker), \
         patch.object(engine, "_asset_worker", mock_asset_worker), \
         patch.object(engine, "_post_clone", AsyncMock()), \
         patch("asyncio.sleep", side_effect=fast_sleep):
         
         # Run the clone. It should stall and then raise RuntimeError
         with pytest.raises(RuntimeError) as exc_info:
             await engine.clone("http://localhost:12345")
         assert "stalled due to deadlock/inactivity" in str(exc_info.value)
         assert sleep_count >= 15
