"""배치 처리용 인메모리 큐."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BatchQueue:
    """배치 처리용 인메모리 큐.

    속성:
        max_size: 배치 최대 크기 (기본 500)
        flush_interval: 자동 플러시 간격 초 (기본 5.0)
    """

    max_size: int = 500
    flush_interval: float = 5.0
    _items: list[dict[str, Any]] = field(default_factory=list)
    _last_flush: float = field(default_factory=time.time)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def add(self, record: dict[str, Any]) -> list[dict[str, Any]] | None:
        """레코드 추가. 플러시 조건 충족 시 배치 반환."""
        async with self._lock:
            self._items.append(record)

            if len(self._items) >= self.max_size:
                return await self._flush_internal()

            if self._should_flush():
                return await self._flush_internal()

            return None

    def _should_flush(self) -> bool:
        """시간 기반 플러시 조건 확인."""
        return (
            len(self._items) > 0
            and (time.time() - self._last_flush) >= self.flush_interval
        )

    async def _flush_internal(self) -> list[dict[str, Any]]:
        """내부 플러시 (락 보유 상태)."""
        batch = self._items
        self._items = []
        self._last_flush = time.time()
        return batch

    async def flush(self) -> list[dict[str, Any]]:
        """강제 플러시."""
        async with self._lock:
            return await self._flush_internal()

    @property
    def pending_count(self) -> int:
        """대기 중인 레코드 수."""
        return len(self._items)
