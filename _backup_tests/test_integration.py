"""Integration TDD 테스트."""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.sync_agent.config import SyncAgentSettings
from src.sync_agent.main import SyncAgent
from src.sync_agent.sync_service import SyncService


@pytest.fixture
def integration_settings(tmp_path: Path) -> SyncAgentSettings:
    """통합 테스트용 설정."""
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    return SyncAgentSettings(
        supabase_url="https://test.supabase.co",
        supabase_service_key="test-key",
        gfx_watch_path=str(watch_dir),
        queue_db_path=str(tmp_path / "queue.db"),
        batch_size=3,
        flush_interval=1.0,
        queue_process_interval=1,
    )


@pytest.fixture
def mock_supabase() -> MagicMock:
    """Supabase Mock."""
    client = MagicMock()
    table_mock = MagicMock()
    table_mock.upsert = MagicMock(return_value=table_mock)
    table_mock.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))
    client.table = MagicMock(return_value=table_mock)
    return client


class TestEndToEnd:
    """전체 플로우 테스트."""

    async def test_end_to_end_sync(
        self,
        integration_settings: SyncAgentSettings,
        mock_supabase: MagicMock,
    ) -> None:
        """파일 생성 → Supabase 동기화."""
        agent = SyncAgent(integration_settings)
        agent.sync_service._client = mock_supabase

        task = asyncio.create_task(agent.start())
        await asyncio.sleep(0.3)

        # 파일 생성
        watch_dir = Path(integration_settings.gfx_watch_path)
        (watch_dir / "session_001.json").write_text(
            json.dumps({"session_id": 1, "event_title": "Test"})
        )
        await asyncio.sleep(1.0)

        await agent.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # upsert 호출 확인
        mock_supabase.table.assert_called_with("gfx_sessions")
        assert mock_supabase.table().upsert.called


class TestOfflineRecovery:
    """장애 복구 테스트."""

    async def test_offline_recovery(
        self,
        integration_settings: SyncAgentSettings,
        mock_supabase: MagicMock,
    ) -> None:
        """오프라인 → 복구 후 동기화."""
        agent = SyncAgent(integration_settings)

        # 1. 네트워크 실패 상황
        mock_supabase.table().upsert().execute = AsyncMock(
            side_effect=Exception("Network error")
        )
        agent.sync_service._client = mock_supabase

        task = asyncio.create_task(agent.start())
        await asyncio.sleep(0.3)

        # 파일 생성 (실패 → 로컬 큐로)
        watch_dir = Path(integration_settings.gfx_watch_path)
        (watch_dir / "session.json").write_text(json.dumps({"session_id": 1}))
        await asyncio.sleep(0.5)

        # 로컬 큐에 저장됨 확인
        count = await agent.local_queue.get_pending_count()
        assert count >= 1

        # 2. 네트워크 복구
        mock_supabase.table().upsert().execute = AsyncMock(
            return_value=MagicMock(data=[{"id": 1}])
        )

        # 3. 오프라인 큐 처리 (1초 후)
        await asyncio.sleep(1.5)

        await agent.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestPerformance:
    """성능 테스트."""

    async def test_batch_performance(
        self,
        integration_settings: SyncAgentSettings,
        mock_supabase: MagicMock,
        tmp_path: Path,
    ) -> None:
        """100건 처리 < 10초."""
        from src.sync_agent.local_queue import LocalQueue

        local_queue = LocalQueue(integration_settings.queue_db_path)
        service = SyncService(integration_settings, local_queue)
        service._client = mock_supabase

        watch_dir = Path(integration_settings.gfx_watch_path)

        start = time.perf_counter()

        # 100건 파일 생성 및 동기화
        for i in range(100):
            json_file = watch_dir / f"session_{i:03d}.json"
            json_file.write_text(json.dumps({"session_id": i}))
            await service.sync_file(str(json_file), "modified")

        await service.flush_batch_queue()

        elapsed = time.perf_counter() - start
        assert elapsed < 10.0, f"100건 처리에 {elapsed:.2f}초 소요 (목표: < 10초)"
