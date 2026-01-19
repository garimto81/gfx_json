"""LocalQueue TDD 테스트."""

import pytest

from src.sync_agent.local_queue import LocalQueue


class TestLocalQueueBasic:
    """기본 CRUD 테스트."""

    async def test_enqueue(self, tmp_queue_db: str) -> None:
        """큐에 추가."""
        queue = LocalQueue(tmp_queue_db)
        await queue.enqueue({"file_hash": "abc123"}, "/path/to/file.json")
        count = await queue.get_pending_count()
        assert count == 1

    async def test_dequeue_batch(self, tmp_queue_db: str) -> None:
        """배치 가져오기."""
        queue = LocalQueue(tmp_queue_db)
        for i in range(10):
            await queue.enqueue({"id": i}, f"/path/{i}.json")

        batch = await queue.dequeue_batch(limit=5)
        assert len(batch) == 5

    async def test_mark_completed(self, tmp_queue_db: str) -> None:
        """완료 처리."""
        queue = LocalQueue(tmp_queue_db)
        await queue.enqueue({"id": 1}, "/path/1.json")

        batch = await queue.dequeue_batch(limit=1)
        queue_id = batch[0]["_queue_id"]

        await queue.mark_completed([queue_id])
        count = await queue.get_pending_count()
        assert count == 0


class TestLocalQueueRetry:
    """재시도 관리 테스트."""

    async def test_mark_failed_increments_retry(self, tmp_queue_db: str) -> None:
        """실패 시 retry_count 증가."""
        queue = LocalQueue(tmp_queue_db)
        await queue.enqueue({"id": 1}, "/path/1.json")

        batch = await queue.dequeue_batch(limit=1)
        queue_id = batch[0]["_queue_id"]

        await queue.mark_failed(queue_id)

        batch2 = await queue.dequeue_batch(limit=1)
        assert batch2[0]["_retry_count"] == 1


class TestLocalQueuePersistence:
    """영속성 테스트."""

    async def test_persistence(self, tmp_path) -> None:
        """재시작 후 데이터 유지."""
        db_path = str(tmp_path / "queue.db")

        queue1 = LocalQueue(db_path)
        await queue1.enqueue({"id": 1}, "/path/1.json")

        # 새 인스턴스로 재연결
        queue2 = LocalQueue(db_path)
        count = await queue2.get_pending_count()
        assert count == 1
