"""FileWatcher TDD 테스트."""

import asyncio
import time
from pathlib import Path

import pytest

from src.sync_agent.file_watcher import WatchfilesWatcher


class TestFileWatcherEvents:
    """이벤트 감지 테스트."""

    async def test_detect_file_created(self, tmp_watch_dir: Path) -> None:
        """파일 생성 감지."""
        created_files: list[str] = []

        async def on_created(path: str) -> None:
            created_files.append(path)

        watcher = WatchfilesWatcher(
            watch_path=str(tmp_watch_dir),
            on_created=on_created,
            on_modified=lambda p: None,
        )

        task = asyncio.create_task(watcher.start())
        await asyncio.sleep(0.2)

        (tmp_watch_dir / "test.json").write_text("{}")
        await asyncio.sleep(0.5)

        await watcher.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(created_files) >= 1
        assert any("test.json" in f for f in created_files)

    async def test_detect_file_modified(self, tmp_watch_dir: Path) -> None:
        """파일 수정 감지."""
        modified_files: list[str] = []
        test_file = tmp_watch_dir / "test.json"
        test_file.write_text("{}")

        async def on_modified(path: str) -> None:
            modified_files.append(path)

        watcher = WatchfilesWatcher(
            watch_path=str(tmp_watch_dir),
            on_created=lambda p: None,
            on_modified=on_modified,
        )

        task = asyncio.create_task(watcher.start())
        await asyncio.sleep(0.2)

        test_file.write_text('{"updated": true}')
        await asyncio.sleep(0.5)

        await watcher.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(modified_files) >= 1


class TestFileWatcherFilter:
    """필터링 테스트."""

    async def test_pattern_filter(self, tmp_watch_dir: Path) -> None:
        """JSON 파일만 감지."""
        created_files: list[str] = []

        watcher = WatchfilesWatcher(
            watch_path=str(tmp_watch_dir),
            on_created=lambda p: created_files.append(p),
            on_modified=lambda p: None,
            file_pattern="*.json",
        )

        task = asyncio.create_task(watcher.start())
        await asyncio.sleep(0.2)

        (tmp_watch_dir / "test.txt").write_text("text")
        (tmp_watch_dir / "test.json").write_text("{}")
        await asyncio.sleep(0.5)

        await watcher.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        json_files = [f for f in created_files if "test.json" in f]
        txt_files = [f for f in created_files if "test.txt" in f]
        assert len(json_files) >= 1
        assert len(txt_files) == 0


class TestFileWatcherLifecycle:
    """시작/중지 테스트."""

    async def test_start_stop(self, tmp_watch_dir: Path) -> None:
        """정상 시작/중지."""
        watcher = WatchfilesWatcher(
            watch_path=str(tmp_watch_dir),
            on_created=lambda p: None,
            on_modified=lambda p: None,
        )

        task = asyncio.create_task(watcher.start())
        await asyncio.sleep(0.2)

        await watcher.stop()
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


class TestFileWatcherPerformance:
    """성능 테스트."""

    async def test_detection_latency(self, tmp_watch_dir: Path) -> None:
        """감지 지연 < 500ms (Windows 여유)."""
        detected = asyncio.Event()
        detection_time: float = 0

        async def on_created(path: str) -> None:
            nonlocal detection_time
            detection_time = time.perf_counter()
            detected.set()

        watcher = WatchfilesWatcher(
            watch_path=str(tmp_watch_dir),
            on_created=on_created,
            on_modified=lambda p: None,
        )

        task = asyncio.create_task(watcher.start())
        await asyncio.sleep(0.2)

        start_time = time.perf_counter()
        (tmp_watch_dir / "latency_test.json").write_text("{}")

        try:
            await asyncio.wait_for(detected.wait(), timeout=5.0)
            latency_ms = (detection_time - start_time) * 1000
            assert latency_ms < 500  # Windows에서 여유 있게
        finally:
            await watcher.stop()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
