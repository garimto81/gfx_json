"""Watcher 모듈 테스트 (PCRegistry, PollingWatcher)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.sync_agent.watcher.polling_watcher import FileEvent, PollingWatcher
from src.sync_agent.watcher.registry import PCInfo, PCRegistry


class TestPCInfo:
    """PCInfo 데이터클래스 테스트."""

    def test_pc_info_creation(self):
        """PCInfo 생성."""
        info = PCInfo(
            pc_id="PC01",
            watch_path=Path("/app/data/PC01/hands"),
            enabled=True,
        )

        assert info.pc_id == "PC01"
        assert info.watch_path == Path("/app/data/PC01/hands")
        assert info.enabled is True

    def test_pc_info_disabled(self):
        """비활성화된 PC."""
        info = PCInfo(
            pc_id="PC02",
            watch_path=Path("/app/data/PC02/hands"),
            enabled=False,
        )

        assert info.enabled is False


class TestPCRegistry:
    """PCRegistry 테스트."""

    @pytest.fixture
    def temp_registry_dir(self, tmp_path: Path):
        """임시 레지스트리 디렉토리."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        return tmp_path

    @pytest.fixture
    def sample_registry(self, temp_registry_dir: Path):
        """샘플 PC 레지스트리 파일 생성."""
        registry_file = temp_registry_dir / "config" / "pc_registry.json"
        data = {
            "pcs": [
                {"id": "PC01", "watch_path": "PC01/hands", "enabled": True},
                {"id": "PC02", "watch_path": "PC02/hands", "enabled": True},
                {"id": "PC03", "watch_path": "PC03/hands", "enabled": False},
            ]
        }
        registry_file.write_text(json.dumps(data), encoding="utf-8")
        return registry_file

    def test_load_registry(self, temp_registry_dir: Path, sample_registry: Path):
        """레지스트리 로드."""
        registry = PCRegistry(
            base_path=str(temp_registry_dir),
            registry_file="config/pc_registry.json",
        )

        pcs = registry.load()

        assert len(pcs) == 2  # enabled만
        assert pcs["PC01"].pc_id == "PC01"
        assert pcs["PC02"].pc_id == "PC02"
        assert "PC03" not in pcs  # disabled

    def test_load_registry_file_not_found(self, temp_registry_dir: Path):
        """레지스트리 파일 없음."""
        registry = PCRegistry(
            base_path=str(temp_registry_dir),
            registry_file="config/nonexistent.json",
        )

        pcs = registry.load()

        assert len(pcs) == 0

    def test_get_enabled_pcs(self, temp_registry_dir: Path, sample_registry: Path):
        """활성화된 PC만 조회."""
        registry = PCRegistry(
            base_path=str(temp_registry_dir),
            registry_file="config/pc_registry.json",
        )
        registry.load()

        enabled = registry.get_enabled_pcs()

        assert len(enabled) == 2
        assert all(pc.enabled for pc in enabled)

    def test_get_pc_ids(self, temp_registry_dir: Path, sample_registry: Path):
        """PC ID 목록 조회."""
        registry = PCRegistry(
            base_path=str(temp_registry_dir),
            registry_file="config/pc_registry.json",
        )
        registry.load()

        pc_ids = registry.get_pc_ids()

        assert "PC01" in pc_ids
        assert "PC02" in pc_ids
        assert "PC03" not in pc_ids

    def test_reload_detects_changes(
        self, temp_registry_dir: Path, sample_registry: Path
    ):
        """레지스트리 변경 감지."""
        registry = PCRegistry(
            base_path=str(temp_registry_dir),
            registry_file="config/pc_registry.json",
        )
        registry.load()

        # 파일 수정
        data = {
            "pcs": [
                {"id": "PC01", "watch_path": "PC01/hands", "enabled": True},
                {"id": "PC04", "watch_path": "PC04/hands", "enabled": True},
            ]
        }
        sample_registry.write_text(json.dumps(data), encoding="utf-8")

        # 리로드
        has_changed = registry.reload()

        assert has_changed is True
        assert "PC04" in registry.get_pc_ids()
        assert "PC02" not in registry.get_pc_ids()

    def test_get_watch_paths(self, temp_registry_dir: Path, sample_registry: Path):
        """감시 경로 목록 조회."""
        registry = PCRegistry(
            base_path=str(temp_registry_dir),
            registry_file="config/pc_registry.json",
        )
        registry.load()

        paths = registry.get_watch_paths()

        assert len(paths) == 2
        assert all(isinstance(p, Path) for p in paths.values())


class TestFileEvent:
    """FileEvent 데이터클래스 테스트."""

    def test_file_event_created(self):
        """created 이벤트."""
        event = FileEvent(
            path="/path/to/file.json",
            event_type="created",
            gfx_pc_id="PC01",
        )

        assert event.path == "/path/to/file.json"
        assert event.event_type == "created"
        assert event.gfx_pc_id == "PC01"

    def test_file_event_modified(self):
        """modified 이벤트."""
        event = FileEvent(
            path="/path/to/file.json",
            event_type="modified",
            gfx_pc_id="PC02",
        )

        assert event.event_type == "modified"


class TestPollingWatcher:
    """PollingWatcher 테스트."""

    @pytest.fixture
    def temp_watch_dir(self, tmp_path: Path):
        """임시 감시 디렉토리."""
        pc01_dir = tmp_path / "PC01" / "hands"
        pc02_dir = tmp_path / "PC02" / "hands"
        pc01_dir.mkdir(parents=True)
        pc02_dir.mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def mock_callback(self):
        """모의 콜백."""
        return AsyncMock()

    def test_init(self, temp_watch_dir: Path, mock_callback):
        """초기화."""
        watcher = PollingWatcher(
            poll_interval=1.0,
            on_event=mock_callback,
        )

        assert watcher.poll_interval == 1.0

    def test_add_watch_path(self, temp_watch_dir: Path, mock_callback):
        """감시 경로 추가."""
        watcher = PollingWatcher(
            poll_interval=1.0,
            on_event=mock_callback,
        )

        pc01_path = temp_watch_dir / "PC01" / "hands"
        watcher.add_watch_path("PC01", pc01_path)

        assert "PC01" in watcher.watch_paths

    def test_remove_watch_path(self, temp_watch_dir: Path, mock_callback):
        """감시 경로 제거."""
        watcher = PollingWatcher(
            poll_interval=1.0,
            on_event=mock_callback,
        )

        pc01_path = temp_watch_dir / "PC01" / "hands"
        watcher.add_watch_path("PC01", pc01_path)
        watcher.remove_watch_path("PC01")

        assert "PC01" not in watcher.watch_paths

    @pytest.mark.asyncio
    async def test_detect_new_file(self, temp_watch_dir: Path, mock_callback):
        """새 파일 감지."""
        watcher = PollingWatcher(
            poll_interval=0.1,
            on_event=mock_callback,
            file_pattern="*.json",
        )

        pc01_path = temp_watch_dir / "PC01" / "hands"
        watcher.add_watch_path("PC01", pc01_path)

        # 초기 스캔
        await watcher._scan_all()

        # 새 파일 생성
        new_file = pc01_path / "session_001.json"
        new_file.write_text('{"session_id": 1}', encoding="utf-8")

        # 재스캔
        await watcher._scan_all()

        # 콜백 호출 확인
        mock_callback.assert_called()
        call_args = mock_callback.call_args
        event = call_args[0][0]
        assert event.event_type == "created"
        assert event.gfx_pc_id == "PC01"

    @pytest.mark.asyncio
    async def test_detect_modified_file(self, temp_watch_dir: Path, mock_callback):
        """파일 수정 감지."""
        watcher = PollingWatcher(
            poll_interval=0.1,
            on_event=mock_callback,
            file_pattern="*.json",
        )

        pc01_path = temp_watch_dir / "PC01" / "hands"
        watcher.add_watch_path("PC01", pc01_path)

        # 기존 파일 생성
        existing_file = pc01_path / "session_001.json"
        existing_file.write_text('{"session_id": 1}', encoding="utf-8")

        # 초기 스캔
        await watcher._scan_all()
        mock_callback.reset_mock()

        # 파일 수정
        time.sleep(0.05)  # mtime 변경 보장
        existing_file.write_text('{"session_id": 1, "updated": true}', encoding="utf-8")

        # 재스캔
        await watcher._scan_all()

        # modified 이벤트 확인
        mock_callback.assert_called()
        event = mock_callback.call_args[0][0]
        assert event.event_type == "modified"

    @pytest.mark.asyncio
    async def test_ignore_non_json_files(self, temp_watch_dir: Path, mock_callback):
        """JSON 외 파일 무시."""
        watcher = PollingWatcher(
            poll_interval=0.1,
            on_event=mock_callback,
            file_pattern="*.json",
        )

        pc01_path = temp_watch_dir / "PC01" / "hands"
        watcher.add_watch_path("PC01", pc01_path)

        # 초기 스캔
        await watcher._scan_all()

        # 비 JSON 파일 생성
        txt_file = pc01_path / "readme.txt"
        txt_file.write_text("This is not JSON", encoding="utf-8")

        # 재스캔
        await watcher._scan_all()

        # 콜백 호출 안됨
        mock_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_pcs(self, temp_watch_dir: Path, mock_callback):
        """여러 PC 동시 감시."""
        watcher = PollingWatcher(
            poll_interval=0.1,
            on_event=mock_callback,
            file_pattern="*.json",
        )

        pc01_path = temp_watch_dir / "PC01" / "hands"
        pc02_path = temp_watch_dir / "PC02" / "hands"
        watcher.add_watch_path("PC01", pc01_path)
        watcher.add_watch_path("PC02", pc02_path)

        # 초기 스캔
        await watcher._scan_all()

        # 각 PC에 파일 생성
        (pc01_path / "pc01_file.json").write_text('{"id": 1}', encoding="utf-8")
        (pc02_path / "pc02_file.json").write_text('{"id": 2}', encoding="utf-8")

        # 재스캔
        await watcher._scan_all()

        # 2번 호출됨
        assert mock_callback.call_count == 2

        # PC ID 확인
        pc_ids = {call[0][0].gfx_pc_id for call in mock_callback.call_args_list}
        assert pc_ids == {"PC01", "PC02"}
