"""BatchQueue TDD 테스트."""

import asyncio

import pytest

from src.sync_agent.batch_queue import BatchQueue


class TestBatchQueueBasic:
    """기본 기능 테스트."""

    async def test_add_single_record(self) -> None:
        """단일 레코드 추가 - 플러시 안됨."""
        queue = BatchQueue(max_size=500)
        result = await queue.add({"id": 1})
        assert result is None
        assert queue.pending_count == 1

    async def test_flush_on_max_size(self) -> None:
        """max_size 도달 시 자동 플러시."""
        queue = BatchQueue(max_size=3)
        await queue.add({"id": 1})
        await queue.add({"id": 2})
        result = await queue.add({"id": 3})
        assert result is not None
        assert len(result) == 3
        assert queue.pending_count == 0

    async def test_manual_flush(self) -> None:
        """수동 플러시."""
        queue = BatchQueue()
        await queue.add({"id": 1})
        await queue.add({"id": 2})
        result = await queue.flush()
        assert len(result) == 2
        assert queue.pending_count == 0

    async def test_empty_flush(self) -> None:
        """빈 큐 플러시."""
        queue = BatchQueue()
        result = await queue.flush()
        assert result == []


class TestBatchQueueInterval:
    """시간 기반 플러시 테스트."""

    async def test_flush_on_interval(self) -> None:
        """시간 경과 시 자동 플러시."""
        queue = BatchQueue(flush_interval=0.1)
        await queue.add({"id": 1})
        await asyncio.sleep(0.15)
        result = await queue.add({"id": 2})
        assert result is not None
        assert len(result) == 2


class TestBatchQueueConcurrency:
    """동시성 테스트."""

    async def test_concurrent_add(self) -> None:
        """동시 추가 안전성."""
        queue = BatchQueue(max_size=100)
        tasks = [queue.add({"id": i}) for i in range(50)]
        await asyncio.gather(*tasks)
        assert queue.pending_count == 50
