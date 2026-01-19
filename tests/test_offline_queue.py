"""OfflineQueue 단위 테스트."""

from __future__ import annotations

import pytest
from src.sync_agent.queue.offline_queue import (
    DeadLetterRecord,
    OfflineQueue,
    QueuedRecord,
)


@pytest.fixture
async def queue(tmp_path):
    """테스트용 OfflineQueue fixture."""
    db_path = str(tmp_path / "test_queue.db")
    q = OfflineQueue(db_path, max_size=100, max_retries=3)
    await q.connect()
    yield q
    await q.close()


class TestOfflineQueueBasic:
    """기본 동작 테스트."""

    @pytest.mark.asyncio
    async def test_connect_creates_tables(self, tmp_path):
        """connect() 시 테이블 생성."""
        db_path = str(tmp_path / "new_queue.db")
        queue = OfflineQueue(db_path)
        await queue.connect()

        # 테이블 존재 확인
        async with queue._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            tables = [row[0] for row in await cursor.fetchall()]

        assert "pending_sync" in tables
        assert "dead_letter" in tables

        await queue.close()

    @pytest.mark.asyncio
    async def test_enqueue_and_count(self, queue):
        """레코드 추가 및 카운트."""
        assert await queue.count() == 0

        record = {"session_id": 1, "file_hash": "abc123"}
        queue_id = await queue.enqueue(record, "PC01", "/path/file.json")

        assert queue_id == 1
        assert await queue.count() == 1

    @pytest.mark.asyncio
    async def test_enqueue_multiple(self, queue):
        """여러 레코드 추가."""
        for i in range(5):
            await queue.enqueue({"id": i}, f"PC0{i % 2 + 1}")

        assert await queue.count() == 5

    @pytest.mark.asyncio
    async def test_dequeue_batch(self, queue):
        """배치 조회."""
        # 3개 추가
        for i in range(3):
            await queue.enqueue({"id": i}, "PC01")

        records = await queue.dequeue_batch(limit=10)

        assert len(records) == 3
        assert all(isinstance(r, QueuedRecord) for r in records)
        assert records[0].record["id"] == 0

    @pytest.mark.asyncio
    async def test_dequeue_orders_by_retry_count(self, queue):
        """재시도 횟수 적은 순서로 조회."""
        # 레코드 추가
        id1 = await queue.enqueue({"id": 1}, "PC01")
        id2 = await queue.enqueue({"id": 2}, "PC01")
        id3 = await queue.enqueue({"id": 3}, "PC01")

        # id2에 실패 마킹 (retry_count 증가)
        await queue.mark_failed(id2, "error")

        records = await queue.dequeue_batch(limit=3)

        # id1, id3이 먼저 (retry_count=0), id2가 마지막 (retry_count=1)
        assert records[0].id == id1
        assert records[1].id == id3
        assert records[2].id == id2


class TestOfflineQueueMarkCompleted:
    """mark_completed 테스트."""

    @pytest.mark.asyncio
    async def test_mark_completed_removes_records(self, queue):
        """완료 마킹 시 레코드 제거."""
        id1 = await queue.enqueue({"id": 1}, "PC01")
        id2 = await queue.enqueue({"id": 2}, "PC01")
        id3 = await queue.enqueue({"id": 3}, "PC01")

        deleted = await queue.mark_completed([id1, id3])

        assert deleted == 2
        assert await queue.count() == 1

    @pytest.mark.asyncio
    async def test_mark_completed_empty_list(self, queue):
        """빈 리스트 처리."""
        await queue.enqueue({"id": 1}, "PC01")

        deleted = await queue.mark_completed([])

        assert deleted == 0
        assert await queue.count() == 1


class TestOfflineQueueMarkFailed:
    """mark_failed 및 Dead Letter Queue 테스트."""

    @pytest.mark.asyncio
    async def test_mark_failed_increments_retry(self, queue):
        """실패 시 retry_count 증가."""
        queue_id = await queue.enqueue({"id": 1}, "PC01")

        moved = await queue.mark_failed(queue_id, "Connection timeout")

        assert moved is False  # max_retries=3이므로 아직 이동 안 함

        records = await queue.dequeue_batch(1)
        assert records[0].retry_count == 1
        assert records[0].last_error == "Connection timeout"

    @pytest.mark.asyncio
    async def test_mark_failed_moves_to_dead_letter(self, queue):
        """max_retries 초과 시 Dead Letter Queue로 이동."""
        queue_id = await queue.enqueue({"id": 1}, "PC01")

        # max_retries=3이므로 2번 실패 후 3번째에 이동
        await queue.mark_failed(queue_id, "error1")
        await queue.mark_failed(queue_id, "error2")
        moved = await queue.mark_failed(queue_id, "error3")

        assert moved is True
        assert await queue.count() == 0
        assert await queue.dead_letter_count() == 1

    @pytest.mark.asyncio
    async def test_get_dead_letters(self, queue):
        """Dead Letter Queue 조회."""
        queue_id = await queue.enqueue(
            {"id": 1, "name": "test"}, "PC01", "/path/file.json"
        )

        # Dead Letter로 이동
        for i in range(3):
            await queue.mark_failed(queue_id, f"error{i}")

        dead_letters = await queue.get_dead_letters()

        assert len(dead_letters) == 1
        assert isinstance(dead_letters[0], DeadLetterRecord)
        assert dead_letters[0].record["name"] == "test"
        assert dead_letters[0].gfx_pc_id == "PC01"
        assert dead_letters[0].retry_count == 3
        assert dead_letters[0].error_reason == "error2"


class TestOfflineQueueRetryDeadLetter:
    """Dead Letter 재시도 테스트."""

    @pytest.mark.asyncio
    async def test_retry_dead_letter(self, queue):
        """Dead Letter 재시도 (메인 큐로 복원)."""
        queue_id = await queue.enqueue({"id": 1}, "PC01")

        # Dead Letter로 이동
        for _ in range(3):
            await queue.mark_failed(queue_id, "error")

        dead_letters = await queue.get_dead_letters()
        dl_id = dead_letters[0].id

        # 재시도
        new_id = await queue.retry_dead_letter(dl_id)

        assert new_id is not None
        assert await queue.count() == 1
        assert await queue.dead_letter_count() == 0

        # 재시도된 레코드는 retry_count=0
        records = await queue.dequeue_batch(1)
        assert records[0].retry_count == 0


class TestOfflineQueueSizeLimit:
    """큐 크기 제한 테스트."""

    @pytest.mark.asyncio
    async def test_enqueue_removes_oldest_when_full(self, tmp_path):
        """큐가 가득 찼을 때 가장 오래된 레코드 제거."""
        db_path = str(tmp_path / "small_queue.db")
        queue = OfflineQueue(db_path, max_size=3, max_retries=5)
        await queue.connect()

        # 3개 추가 (max_size)
        await queue.enqueue({"id": 1}, "PC01")
        await queue.enqueue({"id": 2}, "PC01")
        await queue.enqueue({"id": 3}, "PC01")

        assert await queue.count() == 3

        # 4번째 추가 - 가장 오래된 것 제거됨
        await queue.enqueue({"id": 4}, "PC01")

        assert await queue.count() == 3

        records = await queue.dequeue_batch(10)
        ids = [r.record["id"] for r in records]
        assert 1 not in ids  # 가장 오래된 것 제거됨
        assert 4 in ids  # 새로운 것 추가됨

        await queue.close()


class TestOfflineQueueStats:
    """통계 테스트."""

    @pytest.mark.asyncio
    async def test_get_stats(self, queue):
        """통계 조회."""
        await queue.enqueue({"id": 1}, "PC01")
        await queue.enqueue({"id": 2}, "PC01")
        await queue.enqueue({"id": 3}, "PC02")

        stats = await queue.get_stats()

        assert stats["pending_count"] == 3
        assert stats["dead_letter_count"] == 0
        assert stats["max_size"] == 100
        assert stats["max_retries"] == 3
        assert stats["utilization"] == 0.03
        assert "PC01" in stats["by_pc"]
        assert "PC02" in stats["by_pc"]
        assert stats["by_pc"]["PC01"]["count"] == 2
        assert stats["by_pc"]["PC02"]["count"] == 1


class TestOfflineQueueContextManager:
    """Context Manager 테스트."""

    @pytest.mark.asyncio
    async def test_async_with(self, tmp_path):
        """async with 문 지원."""
        db_path = str(tmp_path / "context_queue.db")

        async with OfflineQueue(db_path) as queue:
            await queue.enqueue({"id": 1}, "PC01")
            assert await queue.count() == 1

        # 연결 종료 확인
        assert queue._db is None


class TestOfflineQueueErrors:
    """오류 처리 테스트."""

    @pytest.mark.asyncio
    async def test_operations_without_connect_raises(self, tmp_path):
        """연결 없이 작업 시 오류."""
        queue = OfflineQueue(str(tmp_path / "no_connect.db"))

        with pytest.raises(RuntimeError, match="연결되지 않음"):
            await queue.enqueue({"id": 1}, "PC01")

    @pytest.mark.asyncio
    async def test_mark_failed_nonexistent_id(self, queue):
        """존재하지 않는 ID 실패 마킹."""
        result = await queue.mark_failed(99999, "error")
        assert result is False

    @pytest.mark.asyncio
    async def test_retry_dead_letter_nonexistent(self, queue):
        """존재하지 않는 Dead Letter 재시도."""
        result = await queue.retry_dead_letter(99999)
        assert result is None
