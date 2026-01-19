"""배치 처리용 인메모리 큐 모듈.

수정된 파일을 배치로 모아서 처리.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BatchQueue:
    """배치 처리용 인메모리 큐.

    기능:
    - 레코드를 모아서 배치로 반환
    - 크기 기반 플러시 (max_size 도달 시)
    - 시간 기반 플러시 (flush_interval 경과 시)
    - 스레드 안전 (asyncio.Lock)

    Examples:
        ```python
        queue = BatchQueue(max_size=100, flush_interval=5.0)

        # 레코드 추가 - 조건 충족 시 배치 반환
        batch = await queue.add({"id": 1})
        if batch:
            await process_batch(batch)

        # 강제 플러시
        remaining = await queue.flush()
        ```
    """

    max_size: int = 500
    flush_interval: float = 5.0
    _items: list[dict[str, Any]] = field(default_factory=list)
    _last_flush: float = field(default_factory=time.time)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _total_added: int = field(default=0)
    _total_flushed: int = field(default=0)

    async def add(self, record: dict[str, Any]) -> list[dict[str, Any]] | None:
        """레코드 추가.

        플러시 조건 충족 시 배치 반환.

        Args:
            record: 추가할 레코드

        Returns:
            배치 (플러시 시) 또는 None
        """
        async with self._lock:
            self._items.append(record)
            self._total_added += 1

            # 크기 기반 플러시
            if len(self._items) >= self.max_size:
                logger.debug(f"크기 기반 플러시: {len(self._items)}건")
                return await self._flush_internal()

            # 시간 기반 플러시
            if self._should_flush():
                logger.debug(f"시간 기반 플러시: {len(self._items)}건")
                return await self._flush_internal()

            return None

    async def flush(self) -> list[dict[str, Any]]:
        """강제 플러시.

        Returns:
            현재 대기 중인 모든 레코드
        """
        async with self._lock:
            if self._items:
                logger.debug(f"강제 플러시: {len(self._items)}건")
            return await self._flush_internal()

    async def _flush_internal(self) -> list[dict[str, Any]]:
        """내부 플러시 (락 보유 상태에서 호출)."""
        batch = self._items
        self._items = []
        self._last_flush = time.time()
        self._total_flushed += len(batch)
        return batch

    def _should_flush(self) -> bool:
        """시간 기반 플러시 조건 확인."""
        if len(self._items) == 0:
            return False
        elapsed = time.time() - self._last_flush
        return elapsed >= self.flush_interval

    @property
    def pending_count(self) -> int:
        """대기 중인 레코드 수."""
        return len(self._items)

    @property
    def is_empty(self) -> bool:
        """큐가 비어있는지 여부."""
        return len(self._items) == 0

    def get_stats(self) -> dict[str, Any]:
        """통계 조회."""
        return {
            "pending_count": self.pending_count,
            "max_size": self.max_size,
            "flush_interval": self.flush_interval,
            "total_added": self._total_added,
            "total_flushed": self._total_flushed,
            "time_since_last_flush": time.time() - self._last_flush,
        }

    def reset_stats(self) -> None:
        """통계 초기화."""
        self._total_added = 0
        self._total_flushed = 0
