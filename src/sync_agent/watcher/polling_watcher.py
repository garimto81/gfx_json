"""SMB 폴링 기반 파일 감시자.

watchdog 기반 폴링으로 SMB/NAS 환경에서 파일 변경 감지.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Literal

logger = logging.getLogger(__name__)


@dataclass
class FileEvent:
    """파일 이벤트."""

    path: str
    event_type: Literal["created", "modified"]
    gfx_pc_id: str


class PollingWatcher:
    """SMB 폴링 기반 파일 감시자.

    SMB/NAS 환경에서는 inotify 같은 OS 이벤트가 작동하지 않으므로
    폴링 방식으로 파일 변경을 감지합니다.

    기능:
    - 여러 PC 경로 동시 감시
    - 파일 패턴 필터링 (*.json)
    - 새 파일 / 수정 파일 구분
    - 비동기 이벤트 콜백

    Examples:
        ```python
        async def on_event(event: FileEvent):
            print(f"{event.gfx_pc_id}: {event.event_type} - {event.path}")

        watcher = PollingWatcher(
            poll_interval=2.0,
            on_event=on_event,
            file_pattern="*.json",
        )

        watcher.add_watch_path("PC01", Path("/app/data/PC01/hands"))
        watcher.add_watch_path("PC02", Path("/app/data/PC02/hands"))

        await watcher.start()
        ```
    """

    def __init__(
        self,
        poll_interval: float = 2.0,
        on_event: Callable[[FileEvent], Coroutine[Any, Any, None]] | None = None,
        file_pattern: str = "*.json",
    ) -> None:
        """초기화.

        Args:
            poll_interval: 폴링 주기 (초)
            on_event: 이벤트 콜백 (async)
            file_pattern: 감시할 파일 패턴
        """
        self.poll_interval = poll_interval
        self._on_event = on_event
        self.file_pattern = file_pattern

        self.watch_paths: dict[str, Path] = {}
        self._file_states: dict[str, dict[str, float]] = {}  # {pc_id: {path: mtime}}
        self._running = False
        self._task: asyncio.Task | None = None

    def add_watch_path(self, pc_id: str, path: Path) -> None:
        """감시 경로 추가.

        Args:
            pc_id: PC 식별자
            path: 감시 경로
        """
        self.watch_paths[pc_id] = path
        self._file_states[pc_id] = {}
        logger.info(f"감시 경로 추가: {pc_id} -> {path}")

    def remove_watch_path(self, pc_id: str) -> None:
        """감시 경로 제거.

        Args:
            pc_id: PC 식별자
        """
        if pc_id in self.watch_paths:
            del self.watch_paths[pc_id]
        if pc_id in self._file_states:
            del self._file_states[pc_id]
        logger.info(f"감시 경로 제거: {pc_id}")

    async def start(self) -> None:
        """감시 시작."""
        self._running = True
        logger.info(f"PollingWatcher 시작 (간격: {self.poll_interval}초)")

        try:
            while self._running:
                await self._scan_all()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            logger.info("PollingWatcher 취소됨")
            raise

    async def stop(self) -> None:
        """감시 중지."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PollingWatcher 중지")

    async def _scan_all(self) -> None:
        """모든 감시 경로 스캔."""
        for pc_id, watch_path in self.watch_paths.items():
            await self._scan_path(pc_id, watch_path)

    async def _scan_path(self, pc_id: str, watch_path: Path) -> None:
        """단일 경로 스캔.

        Args:
            pc_id: PC 식별자
            watch_path: 감시 경로
        """
        if not watch_path.exists():
            return

        current_files: dict[str, float] = {}

        try:
            for file_path in watch_path.glob(self.file_pattern):
                if file_path.is_file():
                    str_path = str(file_path)
                    try:
                        mtime = file_path.stat().st_mtime
                        current_files[str_path] = mtime
                    except OSError:
                        continue

            # 상태 비교
            prev_files = self._file_states.get(pc_id, {})

            # 새 파일
            for path, mtime in current_files.items():
                if path not in prev_files:
                    await self._emit_event(
                        FileEvent(path=path, event_type="created", gfx_pc_id=pc_id)
                    )
                elif mtime > prev_files[path]:
                    await self._emit_event(
                        FileEvent(path=path, event_type="modified", gfx_pc_id=pc_id)
                    )

            # 상태 업데이트
            self._file_states[pc_id] = current_files

        except OSError as e:
            logger.warning(f"경로 스캔 오류 ({pc_id}): {e}")

    async def _emit_event(self, event: FileEvent) -> None:
        """이벤트 발송.

        Args:
            event: 파일 이벤트
        """
        logger.debug(f"파일 이벤트: [{event.gfx_pc_id}] {event.event_type} - {event.path}")

        if self._on_event:
            try:
                await self._on_event(event)
            except Exception as e:
                logger.error(f"이벤트 핸들러 오류: {e}")

    async def scan_existing(self) -> dict[str, list[str]]:
        """기존 파일 전체 스캔 (초기 동기화용).

        Returns:
            {pc_id: [file_paths]} 딕셔너리
        """
        result: dict[str, list[str]] = {}

        for pc_id, watch_path in self.watch_paths.items():
            if not watch_path.exists():
                result[pc_id] = []
                continue

            files = []
            try:
                for file_path in watch_path.glob(self.file_pattern):
                    if file_path.is_file():
                        files.append(str(file_path))
            except OSError as e:
                logger.warning(f"기존 파일 스캔 오류 ({pc_id}): {e}")

            result[pc_id] = files

        total = sum(len(f) for f in result.values())
        logger.info(f"기존 파일 스캔 완료: {total}개")
        return result

    def get_stats(self) -> dict[str, Any]:
        """통계 조회."""
        file_counts = {
            pc_id: len(files) for pc_id, files in self._file_states.items()
        }
        return {
            "running": self._running,
            "poll_interval": self.poll_interval,
            "watched_pcs": list(self.watch_paths.keys()),
            "file_counts": file_counts,
            "total_files": sum(file_counts.values()),
        }
