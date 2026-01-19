"""SyncService TDD 테스트."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.sync_agent.config import SyncAgentSettings
from src.sync_agent.local_queue import LocalQueue
from src.sync_agent.sync_service import SyncService


@pytest.fixture
def settings(tmp_path: Path) -> SyncAgentSettings:
    """테스트용 설정."""
    return SyncAgentSettings(
        supabase_url="https://test.supabase.co",
        supabase_service_key="test-key",
        gfx_watch_path=str(tmp_path / "watch"),
        queue_db_path=str(tmp_path / "queue.db"),
        batch_size=3,
        flush_interval=5.0,
    )


@pytest.fixture
def local_queue(settings: SyncAgentSettings) -> LocalQueue:
    """LocalQueue fixture."""
    return LocalQueue(settings.queue_db_path)


@pytest.fixture
def mock_supabase_client() -> MagicMock:
    """Supabase 클라이언트 Mock."""
    client = MagicMock()
    table_mock = MagicMock()
    table_mock.upsert = MagicMock(return_value=table_mock)
    table_mock.execute = AsyncMock(return_value=MagicMock(data=[{"id": 1}]))
    client.table = MagicMock(return_value=table_mock)
    return client


@pytest.fixture
def sync_service(
    settings: SyncAgentSettings,
    local_queue: LocalQueue,
    mock_supabase_client: MagicMock,
) -> SyncService:
    """SyncService fixture."""
    service = SyncService(settings, local_queue)
    service._client = mock_supabase_client
    return service


@pytest.fixture
def sample_json_file(tmp_path: Path) -> Path:
    """샘플 JSON 파일 생성."""
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir(exist_ok=True)
    json_file = watch_dir / "session_001.json"
    json_file.write_text(json.dumps({
        "session_id": 1,
        "event_title": "Test Event",
        "table_type": "Final",
    }))
    return json_file


class TestSyncServiceRealtime:
    """실시간 경로 테스트."""

    async def test_sync_file_created_immediate(
        self,
        sync_service: SyncService,
        sample_json_file: Path,
    ) -> None:
        """생성 파일 즉시 동기화."""
        await sync_service.sync_file(str(sample_json_file), "created")

        # upsert 호출 확인
        sync_service._client.table.assert_called_with("gfx_sessions")
        sync_service._client.table().upsert.assert_called_once()


class TestSyncServiceBatch:
    """배치 경로 테스트."""

    async def test_sync_file_modified_batched(
        self,
        sync_service: SyncService,
        sample_json_file: Path,
    ) -> None:
        """수정 파일 배치 처리."""
        await sync_service.sync_file(str(sample_json_file), "modified")

        # 아직 upsert 안됨 (배치 대기)
        sync_service._client.table().upsert.assert_not_called()
        assert sync_service.batch_queue.pending_count == 1

    async def test_batch_flush_triggers_upsert(
        self,
        sync_service: SyncService,
        tmp_path: Path,
    ) -> None:
        """배치 플러시 시 upsert."""
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir(exist_ok=True)

        for i in range(3):
            json_file = watch_dir / f"session_{i:03d}.json"
            json_file.write_text(json.dumps({"session_id": i}))
            await sync_service.sync_file(str(json_file), "modified")

        # batch_size=3 이므로 자동 플러시됨
        sync_service._client.table().upsert.assert_called()


class TestSyncServiceOfflineQueue:
    """오프라인 큐 테스트."""

    async def test_network_failure_queues_locally(
        self,
        sync_service: SyncService,
        sample_json_file: Path,
    ) -> None:
        """네트워크 실패 시 로컬 큐."""
        sync_service._client.table().upsert().execute = AsyncMock(
            side_effect=Exception("Network error")
        )

        await sync_service.sync_file(str(sample_json_file), "created")

        count = await sync_service.local_queue.get_pending_count()
        assert count == 1

    async def test_process_offline_queue(
        self,
        sync_service: SyncService,
        sample_json_file: Path,
    ) -> None:
        """오프라인 큐 처리."""
        # 직접 큐에 추가
        await sync_service.local_queue.enqueue(
            {"session_id": 1, "file_hash": "test"},
            str(sample_json_file),
        )

        await sync_service.process_offline_queue()

        # 처리 후 큐 비어있음
        count = await sync_service.local_queue.get_pending_count()
        assert count == 0


class TestSyncServiceDuplicate:
    """중복 처리 테스트."""

    async def test_upsert_handles_duplicate(
        self,
        sync_service: SyncService,
        sample_json_file: Path,
    ) -> None:
        """중복 file_hash upsert."""
        await sync_service.sync_file(str(sample_json_file), "created")
        await sync_service.sync_file(str(sample_json_file), "created")

        # 2번 호출 - 에러 없이 처리
        assert sync_service._client.table().upsert.call_count == 2
