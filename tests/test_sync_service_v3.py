"""SyncService v3.0 테스트.

v3.0 설계:
- NAS 전용 (PC 로컬 모드 제거)
- httpx 기반 SupabaseClient 사용
- Settings 단일 클래스 사용
- 지수 백오프 + jitter
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.sync_agent.config.settings import Settings
from src.sync_agent.core.sync_service_v3 import SyncResult, SyncService
from src.sync_agent.db.supabase_client import (
    RateLimitError,
    SupabaseClient,
    UpsertResult,
)
from src.sync_agent.queues.batch_queue import BatchQueue
from src.sync_agent.queues.offline_queue import OfflineQueue


class TestSyncServiceInit:
    """초기화 테스트."""

    def test_init_with_dependencies(self):
        """의존성 주입 초기화."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
        )
        supabase = MagicMock(spec=SupabaseClient)
        batch_queue = MagicMock(spec=BatchQueue)
        offline_queue = MagicMock(spec=OfflineQueue)

        service = SyncService(
            settings=settings,
            supabase=supabase,
            batch_queue=batch_queue,
            offline_queue=offline_queue,
        )

        assert service.settings == settings
        assert service.supabase == supabase
        assert service.batch_queue == batch_queue
        assert service.offline_queue == offline_queue


class TestSyncFile:
    """sync_file 테스트."""

    @pytest.fixture
    def temp_json_file(self, tmp_path: Path):
        """임시 JSON 파일 생성."""
        data = {
            "session_id": 123,
            "table_type": "NLHE",
            "event_title": "Test Event",
            "hands": [{"id": 1}, {"id": 2}],
        }
        file_path = tmp_path / "test_session.json"
        file_path.write_text(json.dumps(data), encoding="utf-8")
        return file_path

    @pytest.fixture
    def service(self):
        """SyncService 인스턴스."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
        )
        supabase = AsyncMock(spec=SupabaseClient)
        supabase.upsert.return_value = UpsertResult(success=True, count=1)

        batch_queue = BatchQueue(max_size=10, flush_interval=5.0)
        offline_queue = AsyncMock(spec=OfflineQueue)

        return SyncService(
            settings=settings,
            supabase=supabase,
            batch_queue=batch_queue,
            offline_queue=offline_queue,
        )

    @pytest.mark.asyncio
    async def test_sync_file_created_immediate_upsert(
        self, service: SyncService, temp_json_file: Path
    ):
        """created 이벤트는 즉시 upsert."""
        result = await service.sync_file(
            path=str(temp_json_file),
            event_type="created",
            gfx_pc_id="PC01",
        )

        assert result.success is True
        service.supabase.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_file_modified_batch_queue(
        self, service: SyncService, temp_json_file: Path
    ):
        """modified 이벤트는 배치 큐에 추가."""
        result = await service.sync_file(
            path=str(temp_json_file),
            event_type="modified",
            gfx_pc_id="PC01",
        )

        assert result.success is True
        assert result.pending is True
        assert service.batch_queue.pending_count == 1
        service.supabase.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_file_file_not_found(self, service: SyncService):
        """파일 없음 시 에러 반환."""
        result = await service.sync_file(
            path="/nonexistent/file.json",
            event_type="created",
            gfx_pc_id="PC01",
        )

        assert result.success is False
        assert result.error == "file_not_found"

    @pytest.mark.asyncio
    async def test_sync_file_invalid_json(self, service: SyncService, tmp_path: Path):
        """잘못된 JSON 시 에러 폴더로 이동."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ invalid json }", encoding="utf-8")

        with patch.object(
            service, "_move_to_error_folder", new_callable=AsyncMock
        ) as mock_move:
            result = await service.sync_file(
                path=str(bad_file),
                event_type="created",
                gfx_pc_id="PC01",
            )

            assert result.success is False
            assert result.error == "parse_error"
            mock_move.assert_called_once()


class TestRateLimitHandling:
    """Rate Limit 처리 테스트."""

    @pytest.fixture
    def service_with_rate_limit(self):
        """Rate Limit 설정된 SyncService."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
            rate_limit_max_retries=3,
            rate_limit_base_delay=0.1,  # 최소값
        )
        supabase = AsyncMock(spec=SupabaseClient)
        batch_queue = BatchQueue()
        offline_queue = AsyncMock(spec=OfflineQueue)

        return SyncService(
            settings=settings,
            supabase=supabase,
            batch_queue=batch_queue,
            offline_queue=offline_queue,
        )

    @pytest.mark.asyncio
    async def test_rate_limit_retry_success(
        self, service_with_rate_limit: SyncService, tmp_path: Path
    ):
        """Rate Limit 후 재시도 성공."""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"session_id": 1}', encoding="utf-8")

        # 첫 2회 Rate Limit, 3회차 성공
        service_with_rate_limit.supabase.upsert.side_effect = [
            RateLimitError("Rate limit"),
            RateLimitError("Rate limit"),
            UpsertResult(success=True, count=1),
        ]

        result = await service_with_rate_limit.sync_file(
            path=str(json_file),
            event_type="created",
            gfx_pc_id="PC01",
        )

        assert result.success is True
        assert service_with_rate_limit.supabase.upsert.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limit_all_retries_failed(
        self, service_with_rate_limit: SyncService, tmp_path: Path
    ):
        """모든 Rate Limit 재시도 실패 시 오프라인 큐."""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"session_id": 1}', encoding="utf-8")

        # 모든 시도 Rate Limit
        service_with_rate_limit.supabase.upsert.side_effect = RateLimitError(
            "Rate limit"
        )

        result = await service_with_rate_limit.sync_file(
            path=str(json_file),
            event_type="created",
            gfx_pc_id="PC01",
        )

        assert result.success is False
        assert result.error == "rate_limit_exceeded"
        assert result.queued is True
        service_with_rate_limit.offline_queue.enqueue.assert_called_once()


class TestExponentialBackoff:
    """지수 백오프 테스트."""

    def test_calculate_backoff(self):
        """지수 백오프 계산."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
            rate_limit_base_delay=1.0,
        )
        service = SyncService(
            settings=settings,
            supabase=MagicMock(),
            batch_queue=MagicMock(),
            offline_queue=MagicMock(),
        )

        # 지수 증가 확인 (jitter 제외)
        backoff_0 = service._calculate_backoff(0)  # 2^0 * 1.0 = 1.0 + jitter
        backoff_1 = service._calculate_backoff(1)  # 2^1 * 1.0 = 2.0 + jitter
        backoff_2 = service._calculate_backoff(2)  # 2^2 * 1.0 = 4.0 + jitter

        assert 1.0 <= backoff_0 < 2.0
        assert 2.0 <= backoff_1 < 3.0
        assert 4.0 <= backoff_2 < 5.0


class TestBatchProcessing:
    """배치 처리 테스트."""

    @pytest.fixture
    def service_batch(self, tmp_path: Path):
        """배치 테스트용 SyncService."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
        )
        supabase = AsyncMock(spec=SupabaseClient)
        supabase.upsert.return_value = UpsertResult(success=True, count=1)

        batch_queue = BatchQueue(max_size=3, flush_interval=60.0)
        offline_queue = AsyncMock(spec=OfflineQueue)

        return SyncService(
            settings=settings,
            supabase=supabase,
            batch_queue=batch_queue,
            offline_queue=offline_queue,
        )

    @pytest.mark.asyncio
    async def test_batch_flush_on_max_size(
        self, service_batch: SyncService, tmp_path: Path
    ):
        """max_size 도달 시 배치 플러시."""
        files = []
        for i in range(3):
            f = tmp_path / f"file{i}.json"
            f.write_text(f'{{"session_id": {i}}}', encoding="utf-8")
            files.append(f)

        # 2개 추가 - 아직 플러시 안됨
        await service_batch.sync_file(str(files[0]), "modified", "PC01")
        await service_batch.sync_file(str(files[1]), "modified", "PC01")
        assert service_batch.supabase.upsert.call_count == 0

        # 3번째 추가 - 플러시 발생
        await service_batch.sync_file(str(files[2]), "modified", "PC01")
        service_batch.supabase.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_flush_batch_queue_manual(
        self, service_batch: SyncService, tmp_path: Path
    ):
        """수동 배치 플러시."""
        f = tmp_path / "file.json"
        f.write_text('{"session_id": 1}', encoding="utf-8")

        await service_batch.sync_file(str(f), "modified", "PC01")
        assert service_batch.supabase.upsert.call_count == 0

        await service_batch.flush_batch_queue()
        service_batch.supabase.upsert.assert_called_once()


class TestOfflineQueueIntegration:
    """오프라인 큐 통합 테스트."""

    @pytest.fixture
    def service_offline(self, tmp_path: Path):
        """오프라인 큐 테스트용 SyncService."""
        settings = Settings(
            supabase_url="https://test.supabase.co",
            supabase_secret_key="test_key",
        )
        supabase = AsyncMock(spec=SupabaseClient)
        batch_queue = BatchQueue()
        offline_queue = AsyncMock(spec=OfflineQueue)

        return SyncService(
            settings=settings,
            supabase=supabase,
            batch_queue=batch_queue,
            offline_queue=offline_queue,
        )

    @pytest.mark.asyncio
    async def test_network_error_enqueues(
        self, service_offline: SyncService, tmp_path: Path
    ):
        """네트워크 오류 시 오프라인 큐에 추가."""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"session_id": 1}', encoding="utf-8")

        service_offline.supabase.upsert.side_effect = Exception("Connection failed")

        result = await service_offline.sync_file(
            path=str(json_file),
            event_type="created",
            gfx_pc_id="PC01",
        )

        assert result.success is False
        assert result.queued is True
        service_offline.offline_queue.enqueue.assert_called_once()


class TestSyncResult:
    """SyncResult 데이터클래스 테스트."""

    def test_sync_result_success(self):
        """성공 결과."""
        result = SyncResult(success=True)
        assert result.success is True
        assert result.error is None
        assert result.pending is False
        assert result.queued is False

    def test_sync_result_failure(self):
        """실패 결과."""
        result = SyncResult(success=False, error="parse_error")
        assert result.success is False
        assert result.error == "parse_error"

    def test_sync_result_pending(self):
        """대기 중 결과."""
        result = SyncResult(success=True, pending=True)
        assert result.success is True
        assert result.pending is True

    def test_sync_result_queued(self):
        """큐에 추가된 결과."""
        result = SyncResult(success=False, error="network", queued=True)
        assert result.queued is True
