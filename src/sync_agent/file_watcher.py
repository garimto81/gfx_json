"""watchfiles 기반 파일 감시자."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from watchfiles import Change, awatch

logger = logging.getLogger(__name__)


class WatchfilesWatcher:
    """watchfiles 기반 파일 감시자.

    Rust(Notify) 기반으로 OS 네이티브 API 사용:
    - Windows: ReadDirectoryChangesW
    - Linux: inotify
    - macOS: FSEvents

    폴링 방식 대비:
    - 감지 지연: ~2초 → ~1ms
    - CPU 사용: 높음 → 최소
    """

    def __init__(
        self,
        watch_path: str,
        on_created: Callable[[str], Coroutine[Any, Any, None]],
        on_modified: Callable[[str], Coroutine[Any, Any, None]],
        file_pattern: str = "*.json",
    ) -> None:
        """초기화.

        Args:
            watch_path: 감시할 디렉토리 경로
            on_created: 파일 생성 시 콜백 (async)
            on_modified: 파일 수정 시 콜백 (async)
            file_pattern: 감시할 파일 패턴
        """
        self.watch_path = Path(watch_path)
        self.on_created = on_created
        self.on_modified = on_modified
        self.file_pattern = file_pattern
        self._running = False
        self._stop_event: asyncio.Event | None = None

    def _match_pattern(self, path: str) -> bool:
        """파일 패턴 매칭."""
        return Path(path).match(self.file_pattern)

    async def start(self) -> None:
        """파일 감시 시작."""
        self._running = True
        self._stop_event = asyncio.Event()
        logger.info(f"watchfiles 감시 시작: {self.watch_path}")

        try:
            async for changes in awatch(
                self.watch_path,
                stop_event=self._stop_event,
                debounce=50,
                step=50,
            ):
                if not self._running:
                    break

                for change_type, path in changes:
                    if not self._match_pattern(path):
                        continue

                    try:
                        if change_type == Change.added:
                            logger.debug(f"파일 생성 감지: {path}")
                            await self.on_created(path)
                        elif change_type == Change.modified:
                            logger.debug(f"파일 수정 감지: {path}")
                            await self.on_modified(path)
                    except Exception as e:
                        logger.error(f"이벤트 처리 실패 ({path}): {e}")
        except asyncio.CancelledError:
            logger.info("watchfiles 감시 취소됨")
            raise

    async def stop(self) -> None:
        """파일 감시 중지."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        logger.info("watchfiles 감시 중지")
