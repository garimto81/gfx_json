"""SyncAgent v3.0 - NAS 동기화 에이전트.

v3.0 설계:
- NAS 전용 (PC 로컬 모드 제거)
- 4개 태스크 병렬 실행
- 시작 시 전체 스캔
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.sync_agent.config.settings import Settings
from src.sync_agent.core.json_parser import JsonParser
from src.sync_agent.core.sync_service_v3 import SyncService
from src.sync_agent.db.supabase_client import SupabaseClient
from src.sync_agent.queues.batch_queue import BatchQueue
from src.sync_agent.queues.offline_queue import OfflineQueue
from src.sync_agent.watcher.polling_watcher import FileEvent, PollingWatcher
from src.sync_agent.watcher.registry import PCRegistry

logger = logging.getLogger(__name__)


class SyncAgent:
    """NAS 동기화 에이전트.

    기능:
    - PC 레지스트리 기반 다중 폴더 감시
    - 파일 이벤트 → SyncService 연계
    - 시작 시 기존 파일 전체 스캔
    - 오프라인 큐 주기적 처리
    - 레지스트리 변경 감시

    Examples:
        ```python
        settings = Settings()
        agent = SyncAgent(settings=settings)

        await agent.start()  # 4개 태스크 병렬 실행
        await agent.stop()   # graceful shutdown
        ```
    """

    def __init__(self, settings: Settings) -> None:
        """초기화.

        Args:
            settings: 설정
        """
        self.settings = settings
        self._running = False

        # 컴포넌트 초기화
        self.supabase = SupabaseClient(
            url=settings.supabase_url,
            secret_key=settings.supabase_secret_key,
            timeout=settings.supabase_timeout,
        )

        self.offline_queue = OfflineQueue(
            db_path=settings.queue_db_path,
            max_size=settings.max_queue_size,
            max_retries=settings.max_retries,
        )

        self.batch_queue = BatchQueue(
            max_size=settings.batch_size,
            flush_interval=settings.flush_interval,
        )

        self.json_parser = JsonParser()

        self.sync_service = SyncService(
            settings=settings,
            supabase=self.supabase,
            batch_queue=self.batch_queue,
            offline_queue=self.offline_queue,
            json_parser=self.json_parser,
        )

        self.registry = PCRegistry(
            base_path=settings.nas_base_path,
            registry_file=settings.registry_path,
        )

        self.watcher = PollingWatcher(
            poll_interval=settings.poll_interval,
            on_event=self._handle_file_event,
            file_pattern=settings.file_pattern,
        )

    async def start(self) -> None:
        """에이전트 시작 - 4개 태스크 병렬 실행."""
        self._running = True
        logger.info("=" * 60)
        logger.info("SyncAgent v3.0 시작")
        logger.info("=" * 60)
        logger.info(f"NAS 경로: {self.settings.nas_base_path}")
        logger.info(f"Supabase: {self.settings.supabase_url[:30]}...")
        logger.info(f"폴링 주기: {self.settings.poll_interval}초")
        logger.info("=" * 60)

        # Supabase 연결
        await self.supabase.connect()

        # 오프라인 큐 연결
        await self.offline_queue.connect()

        # PC 레지스트리 로드
        self.registry.load()
        for pc_id, path in self.registry.get_watch_paths().items():
            self.watcher.add_watch_path(pc_id, path)
            logger.info(f"감시 등록: {pc_id} -> {path}")

        # 4개 태스크 병렬 실행
        try:
            await asyncio.gather(
                self._scan_existing_files(),  # 시작 시 전체 스캔
                self.watcher.start(),  # 파일 감시
                self._process_offline_queue_loop(),  # 오프라인 큐 처리
                self._watch_registry_changes(),  # PC 레지스트리 감시
            )
        except asyncio.CancelledError:
            logger.info("SyncAgent 태스크 취소됨")
            raise

    async def _scan_existing_files(self) -> None:
        """시작 시 기존 파일 전체 스캔 (폴링 누락 방지)."""
        existing = await self.watcher.scan_existing()

        total = sum(len(files) for files in existing.values())
        if total == 0:
            logger.info("기존 동기화할 파일 없음")
            return

        logger.info(f"기존 파일 동기화 시작: {total}개")

        for pc_id, file_paths in existing.items():
            for path in file_paths:
                await self.sync_service.sync_file(
                    path=path,
                    event_type="created",
                    gfx_pc_id=pc_id,
                )

        logger.info("기존 파일 동기화 완료")

    async def _handle_file_event(self, event: FileEvent) -> None:
        """파일 이벤트 처리.

        Args:
            event: 파일 이벤트
        """
        await self.sync_service.sync_file(
            path=event.path,
            event_type=event.event_type,
            gfx_pc_id=event.gfx_pc_id,
        )

    async def _process_offline_queue_loop(self) -> None:
        """오프라인 큐 주기적 처리."""
        while self._running:
            try:
                await asyncio.sleep(self.settings.queue_process_interval)
                await self._process_offline_queue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"오프라인 큐 처리 오류: {e}")

    async def _process_offline_queue(self) -> None:
        """오프라인 큐 단일 처리."""
        batch = await self.offline_queue.dequeue_batch(limit=50)
        if not batch:
            return

        logger.info(f"오프라인 큐 처리 시작: {len(batch)}건")

        records = []
        queue_ids = []
        for item in batch:
            records.append(item.record)
            queue_ids.append(item.id)

        try:
            result = await self.supabase.upsert(
                table=self.settings.supabase_table,
                records=records,
                on_conflict="session_id",
            )

            if result.success:
                await self.offline_queue.mark_completed(queue_ids)
                logger.info(f"오프라인 큐 처리 완료: {len(batch)}건")
            else:
                for item in batch:
                    await self.offline_queue.mark_failed(
                        item.id, result.error or "unknown"
                    )
                logger.warning(f"오프라인 큐 처리 실패: {result.error}")

        except Exception as e:
            logger.error(f"오프라인 큐 처리 오류: {e}")
            for item in batch:
                await self.offline_queue.mark_failed(item.id, str(e))

    async def _watch_registry_changes(self) -> None:
        """PC 레지스트리 변경 감시."""
        check_interval = 30  # 30초마다 확인

        while self._running:
            try:
                await asyncio.sleep(check_interval)

                if self.registry.reload():
                    logger.info("PC 레지스트리 변경 감지, 감시 경로 업데이트")
                    await self._update_watch_paths()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"레지스트리 감시 오류: {e}")

    async def _update_watch_paths(self) -> None:
        """감시 경로 업데이트."""
        current_pcs = set(self.watcher.watch_paths.keys())
        new_pcs = set(self.registry.get_pc_ids())

        # 새로 추가된 PC
        for pc_id in new_pcs - current_pcs:
            pc = self.registry.get_pc(pc_id)
            if pc:
                self.watcher.add_watch_path(pc_id, pc.watch_path)
                logger.info(f"PC 추가: {pc_id}")

        # 제거된 PC
        for pc_id in current_pcs - new_pcs:
            self.watcher.remove_watch_path(pc_id)
            logger.info(f"PC 제거: {pc_id}")

    async def stop(self) -> None:
        """에이전트 중지 (graceful shutdown)."""
        logger.info("SyncAgent 중지 시작...")
        self._running = False

        # 감시자 중지
        await self.watcher.stop()

        # 배치 큐 플러시
        await self.sync_service.flush_batch_queue()

        # 연결 종료
        await self.offline_queue.close()
        await self.supabase.close()

        logger.info("SyncAgent 중지 완료")

    def get_stats(self) -> dict[str, Any]:
        """상태 통계 조회."""
        return {
            "running": self._running,
            "settings": {
                "nas_base_path": self.settings.nas_base_path,
                "poll_interval": self.settings.poll_interval,
            },
            "watcher": self.watcher.get_stats(),
            "batch_queue": self.batch_queue.get_stats(),
            "registry": {
                "pc_count": len(self.registry.get_pc_ids()),
                "pcs": self.registry.get_pc_ids(),
            },
        }
