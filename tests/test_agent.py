"""SyncAgent v3.0 테스트."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.sync_agent.config.settings import Settings
from src.sync_agent.core.agent import SyncAgent
from src.sync_agent.core.sync_service_v3 import SyncResult, SyncService
from src.sync_agent.queue.batch_queue import BatchQueue
from src.sync_agent.queue.offline_queue import OfflineQueue
from src.sync_agent.watcher.polling_watcher import FileEvent, PollingWatcher
from src.sync_agent.watcher.registry import PCRegistry


class TestSyncAgentInit:
    """초기화 테스트."""

    def test_init_with_settings(self, tmp_path: Path):
        """Settings로 초기화."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
            nas_base_path=str(tmp_path),
        )

        agent = SyncAgent(settings=settings)

        assert agent.settings == settings
        assert agent.watcher is not None
        assert agent.sync_service is not None
        assert agent.registry is not None


class TestSyncAgentStart:
    """start 테스트."""

    @pytest.fixture
    def temp_nas(self, tmp_path: Path):
        """임시 NAS 구조."""
        # config 디렉토리
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # PC 레지스트리
        registry = {
            "pcs": [
                {"id": "PC01", "watch_path": "PC01/hands", "enabled": True},
            ]
        }
        (config_dir / "pc_registry.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )

        # PC 데이터 디렉토리
        pc01_dir = tmp_path / "PC01" / "hands"
        pc01_dir.mkdir(parents=True)

        return tmp_path

    @pytest.mark.asyncio
    async def test_start_loads_registry(self, temp_nas: Path):
        """시작 시 레지스트리 로드."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
            nas_base_path=str(temp_nas),
        )

        agent = SyncAgent(settings=settings)

        # 짧은 시간 후 중지
        async def stop_soon():
            await asyncio.sleep(0.1)
            await agent.stop()

        with patch.object(agent.sync_service.supabase, "connect", new_callable=AsyncMock):
            with patch.object(agent.offline_queue, "connect", new_callable=AsyncMock):
                task = asyncio.create_task(agent.start())
                await stop_soon()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # 레지스트리가 로드됨
        assert "PC01" in agent.registry.get_pc_ids()


class TestSyncAgentEventHandling:
    """이벤트 처리 테스트."""

    @pytest.fixture
    def agent(self, tmp_path: Path):
        """테스트용 에이전트."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
            nas_base_path=str(tmp_path),
        )
        agent = SyncAgent(settings=settings)
        agent.sync_service = AsyncMock(spec=SyncService)
        agent.sync_service.sync_file = AsyncMock(return_value=SyncResult(success=True))
        return agent

    @pytest.mark.asyncio
    async def test_handle_file_event_created(self, agent: SyncAgent, tmp_path: Path):
        """created 이벤트 처리."""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"id": 1}', encoding="utf-8")

        event = FileEvent(
            path=str(json_file),
            event_type="created",
            gfx_pc_id="PC01",
        )

        await agent._handle_file_event(event)

        agent.sync_service.sync_file.assert_called_once_with(
            path=str(json_file),
            event_type="created",
            gfx_pc_id="PC01",
        )

    @pytest.mark.asyncio
    async def test_handle_file_event_modified(self, agent: SyncAgent, tmp_path: Path):
        """modified 이벤트 처리."""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"id": 1}', encoding="utf-8")

        event = FileEvent(
            path=str(json_file),
            event_type="modified",
            gfx_pc_id="PC01",
        )

        await agent._handle_file_event(event)

        agent.sync_service.sync_file.assert_called_once_with(
            path=str(json_file),
            event_type="modified",
            gfx_pc_id="PC01",
        )


class TestSyncAgentInitialSync:
    """초기 동기화 테스트."""

    @pytest.fixture
    def temp_nas_with_files(self, tmp_path: Path):
        """기존 파일이 있는 임시 NAS."""
        # config 디렉토리
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # PC 레지스트리
        registry = {"pcs": [{"id": "PC01", "watch_path": "PC01/hands", "enabled": True}]}
        (config_dir / "pc_registry.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )

        # PC 데이터 디렉토리와 기존 파일
        pc01_dir = tmp_path / "PC01" / "hands"
        pc01_dir.mkdir(parents=True)

        (pc01_dir / "session_001.json").write_text('{"session_id": 1}', encoding="utf-8")
        (pc01_dir / "session_002.json").write_text('{"session_id": 2}', encoding="utf-8")

        return tmp_path

    @pytest.mark.asyncio
    async def test_scan_existing_files(self, temp_nas_with_files: Path):
        """기존 파일 스캔."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
            nas_base_path=str(temp_nas_with_files),
        )

        agent = SyncAgent(settings=settings)
        agent.registry.load()

        # watcher에 경로 추가
        for pc_id, path in agent.registry.get_watch_paths().items():
            agent.watcher.add_watch_path(pc_id, path)

        # 기존 파일 스캔
        existing = await agent.watcher.scan_existing()

        assert "PC01" in existing
        assert len(existing["PC01"]) == 2


class TestSyncAgentStop:
    """stop 테스트."""

    @pytest.mark.asyncio
    async def test_stop_flushes_batch_queue(self, tmp_path: Path):
        """중지 시 배치 큐 플러시."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
            nas_base_path=str(tmp_path),
        )

        agent = SyncAgent(settings=settings)
        agent.sync_service = AsyncMock(spec=SyncService)

        await agent.stop()

        agent.sync_service.flush_batch_queue.assert_called_once()


class TestSyncAgentOfflineQueue:
    """오프라인 큐 처리 테스트."""

    @pytest.mark.asyncio
    async def test_process_offline_queue_periodically(self, tmp_path: Path):
        """오프라인 큐 주기적 처리."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
            nas_base_path=str(tmp_path),
            queue_process_interval=10,  # 10초
        )

        agent = SyncAgent(settings=settings)

        # queue_process_interval 확인
        assert agent.settings.queue_process_interval == 10
