"""다중 경로 SMB 폴더 감시자.

watchdog PollingObserver를 사용하여 여러 GFX PC의 폴더를 동시에 감시합니다.
watchfiles(Rust 기반)는 SMB/NAS를 지원하지 않으므로 폴링 방식 사용.

사용 예:
    watcher = MultiPathWatcher(
        base_path="/mnt/nas/gfx_data",
        on_created=handle_created,
        on_modified=handle_modified,
    )
    watcher.add_pc("PC01", "PC01/hands")
    watcher.add_pc("PC02", "PC02/hands")
    await watcher.start()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from watchdog.events import (
    FileCreatedEvent,
    FileModifiedEvent,
    FileSystemEventHandler,
)
from watchdog.observers.polling import PollingObserver

logger = logging.getLogger(__name__)


@dataclass
class WatchedPC:
    """감시 대상 PC 정보."""

    pc_id: str
    watch_path: Path
    enabled: bool = True


class MultiPathHandler(FileSystemEventHandler):
    """다중 경로 이벤트 핸들러.

    watchdog 이벤트를 받아서 asyncio 콜백으로 변환합니다.
    """

    def __init__(
        self,
        pc_id: str,
        on_created_callback: Callable[[str, str], Coroutine[Any, Any, None]],
        on_modified_callback: Callable[[str, str], Coroutine[Any, Any, None]],
        file_pattern: str = "*.json",
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """초기화.

        Args:
            pc_id: GFX PC 식별자
            on_created_callback: 파일 생성 시 콜백 (path, pc_id)
            on_modified_callback: 파일 수정 시 콜백 (path, pc_id)
            file_pattern: 감시할 파일 패턴
            loop: asyncio 이벤트 루프
        """
        super().__init__()
        self.pc_id = pc_id
        self._on_created_callback = on_created_callback
        self._on_modified_callback = on_modified_callback
        self.file_pattern = file_pattern
        self.loop = loop
        self._processed_paths: set[str] = set()

    def _match_pattern(self, path: str) -> bool:
        """파일 패턴 매칭."""
        return Path(path).match(self.file_pattern)

    def _run_async(
        self,
        coro: Coroutine[Any, Any, None],
    ) -> None:
        """asyncio 코루틴을 스레드 안전하게 실행."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            logger.warning("이벤트 루프가 실행 중이 아닙니다")

    def on_created(self, event: FileCreatedEvent) -> None:
        """파일 생성 이벤트."""
        if event.is_directory:
            return
        if not self._match_pattern(event.src_path):
            return

        # 중복 이벤트 방지 (watchdog이 때때로 중복 이벤트 발생)
        if event.src_path in self._processed_paths:
            return
        self._processed_paths.add(event.src_path)

        # 오래된 경로 정리 (메모리 누수 방지)
        if len(self._processed_paths) > 1000:
            self._processed_paths.clear()

        logger.debug(f"[{self.pc_id}] 파일 생성 감지: {event.src_path}")
        self._run_async(self._on_created_callback(event.src_path, self.pc_id))

    def on_modified(self, event: FileModifiedEvent) -> None:
        """파일 수정 이벤트."""
        if event.is_directory:
            return
        if not self._match_pattern(event.src_path):
            return

        logger.debug(f"[{self.pc_id}] 파일 수정 감지: {event.src_path}")
        self._run_async(self._on_modified_callback(event.src_path, self.pc_id))


class MultiPathWatcher:
    """다중 경로 SMB 폴더 감시자.

    여러 GFX PC의 폴더를 동시에 감시하고,
    파일 이벤트 발생 시 지정된 콜백을 호출합니다.

    Attributes:
        base_path: NAS 공유 폴더 기본 경로
        poll_interval: 폴링 주기 (초)
        watched_pcs: 감시 대상 PC 딕셔너리
    """

    def __init__(
        self,
        base_path: str,
        on_created: Callable[[str, str], Coroutine[Any, Any, None]],
        on_modified: Callable[[str, str], Coroutine[Any, Any, None]],
        poll_interval: float = 2.0,
        file_pattern: str = "*.json",
    ) -> None:
        """초기화.

        Args:
            base_path: NAS 공유 폴더 기본 경로
            on_created: 파일 생성 시 콜백 (path, pc_id)
            on_modified: 파일 수정 시 콜백 (path, pc_id)
            poll_interval: 폴링 주기 (초, 기본 2.0)
            file_pattern: 감시할 파일 패턴 (기본 *.json)
        """
        self.base_path = Path(base_path)
        self.on_created = on_created
        self.on_modified = on_modified
        self.poll_interval = poll_interval
        self.file_pattern = file_pattern

        self.watched_pcs: dict[str, WatchedPC] = {}
        self._observer: PollingObserver | None = None
        self._running = False
        self._handlers: dict[str, MultiPathHandler] = {}

    def add_pc(self, pc_id: str, sub_path: str) -> bool:
        """감시 대상 PC 추가.

        Args:
            pc_id: GFX PC 식별자 (예: "PC01")
            sub_path: 기본 경로 대비 상대 경로 (예: "PC01/hands")

        Returns:
            성공 여부
        """
        watch_path = self.base_path / sub_path

        # 디렉토리가 없으면 생성
        if not watch_path.exists():
            try:
                watch_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"디렉토리 생성: {watch_path}")
            except OSError as e:
                logger.error(f"디렉토리 생성 실패: {watch_path}, {e}")
                return False

        self.watched_pcs[pc_id] = WatchedPC(
            pc_id=pc_id,
            watch_path=watch_path,
        )
        logger.info(f"PC 추가: {pc_id} -> {watch_path}")
        return True

    def remove_pc(self, pc_id: str) -> bool:
        """감시 대상 PC 제거.

        Args:
            pc_id: GFX PC 식별자

        Returns:
            성공 여부
        """
        if pc_id not in self.watched_pcs:
            logger.warning(f"등록되지 않은 PC: {pc_id}")
            return False

        del self.watched_pcs[pc_id]
        logger.info(f"PC 제거: {pc_id}")

        # 실행 중이면 핸들러도 제거 (observer 재시작 필요)
        if pc_id in self._handlers:
            del self._handlers[pc_id]

        return True

    def get_pc_ids(self) -> list[str]:
        """등록된 PC ID 목록 반환."""
        return list(self.watched_pcs.keys())

    def get_pc_status(self, pc_id: str) -> dict[str, Any] | None:
        """PC 상태 정보 반환."""
        if pc_id not in self.watched_pcs:
            return None

        pc = self.watched_pcs[pc_id]
        return {
            "pc_id": pc.pc_id,
            "watch_path": str(pc.watch_path),
            "enabled": pc.enabled,
            "exists": pc.watch_path.exists(),
        }

    async def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """감시 시작.

        Args:
            loop: asyncio 이벤트 루프 (None이면 현재 루프 사용)
        """
        if not self.watched_pcs:
            logger.warning("등록된 PC가 없습니다. 감시를 시작하지 않습니다.")
            return

        if loop is None:
            loop = asyncio.get_running_loop()

        self._running = True
        self._observer = PollingObserver(timeout=self.poll_interval)

        # 각 PC 폴더에 핸들러 등록
        for pc_id, pc_info in self.watched_pcs.items():
            if not pc_info.enabled:
                logger.info(f"[{pc_id}] 비활성화 상태, 건너뜀")
                continue

            if not pc_info.watch_path.exists():
                logger.warning(f"[{pc_id}] 경로 없음: {pc_info.watch_path}")
                continue

            handler = MultiPathHandler(
                pc_id=pc_id,
                on_created_callback=self.on_created,
                on_modified_callback=self.on_modified,
                file_pattern=self.file_pattern,
                loop=loop,
            )
            self._handlers[pc_id] = handler

            self._observer.schedule(
                handler,
                str(pc_info.watch_path),
                recursive=True,
            )
            logger.info(
                f"감시 등록: [{pc_id}] {pc_info.watch_path} "
                f"(폴링 주기: {self.poll_interval}초)"
            )

        self._observer.start()
        logger.info(
            f"MultiPathWatcher 시작: {len(self._handlers)}개 PC, "
            f"폴링 주기 {self.poll_interval}초"
        )

        # 감시 유지 (중지 신호까지 대기)
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("감시 태스크 취소됨")
            self.stop()

    def stop(self) -> None:
        """감시 중지."""
        self._running = False

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        self._handlers.clear()
        logger.info("MultiPathWatcher 중지 완료")

    @property
    def is_running(self) -> bool:
        """실행 상태 확인."""
        return self._running and self._observer is not None


async def scan_existing_files(
    base_path: str,
    pc_ids: list[str],
    file_pattern: str = "*.json",
) -> dict[str, list[str]]:
    """기존 파일 스캔 (초기 동기화용).

    Args:
        base_path: NAS 기본 경로
        pc_ids: 스캔할 PC ID 목록
        file_pattern: 파일 패턴

    Returns:
        PC별 파일 경로 딕셔너리
    """
    base = Path(base_path)
    result: dict[str, list[str]] = {}

    for pc_id in pc_ids:
        pc_path = base / pc_id / "hands"
        if not pc_path.exists():
            result[pc_id] = []
            continue

        files = list(pc_path.glob(file_pattern))
        result[pc_id] = [str(f) for f in files]
        logger.info(f"[{pc_id}] 기존 파일 {len(files)}개 발견")

    return result
