"""SyncAgent 메인 진입점."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any

from src.sync_agent.config import CentralSyncSettings, SyncAgentSettings
from src.sync_agent.file_watcher import WatchfilesWatcher
from src.sync_agent.local_queue import LocalQueue
from src.sync_agent.multi_path_watcher import MultiPathWatcher, scan_existing_files
from src.sync_agent.sync_service import CentralSyncService, SyncService

logger = logging.getLogger(__name__)


class SyncAgent:
    """GFX JSON → Supabase 동기화 에이전트."""

    def __init__(self, settings: SyncAgentSettings) -> None:
        """초기화.

        Args:
            settings: 설정
        """
        self.settings = settings
        self.local_queue = LocalQueue(settings.queue_db_path)
        self.sync_service = SyncService(settings, self.local_queue)
        self.watcher: WatchfilesWatcher | None = None
        self._running = False

    async def start(self) -> None:
        """에이전트 시작."""
        self._running = True
        logger.info("SyncAgent 시작")

        # watchfiles 기반 파일 감시자 초기화
        self.watcher = WatchfilesWatcher(
            watch_path=self.settings.gfx_watch_path,
            on_created=self._handle_created,
            on_modified=self._handle_modified,
            file_pattern="*.json",
        )

        # 병렬 실행: 파일 감시 + 오프라인 큐 처리
        try:
            await asyncio.gather(
                self.watcher.start(),
                self._process_offline_queue_loop(),
            )
        except asyncio.CancelledError:
            logger.info("SyncAgent 태스크 취소됨")
            raise

    async def _handle_created(self, path: str) -> None:
        """파일 생성 이벤트 처리 (실시간 경로).

        Args:
            path: 생성된 파일 경로
        """
        await self.sync_service.sync_file(path, "created")

    async def _handle_modified(self, path: str) -> None:
        """파일 수정 이벤트 처리 (배치 경로).

        Args:
            path: 수정된 파일 경로
        """
        await self.sync_service.sync_file(path, "modified")

    async def _process_offline_queue_loop(self) -> None:
        """오프라인 큐 주기적 처리."""
        while self._running:
            try:
                await asyncio.sleep(self.settings.queue_process_interval)
                await self.sync_service.process_offline_queue()
            except asyncio.CancelledError:
                break

    async def stop(self) -> None:
        """에이전트 중지."""
        self._running = False

        if self.watcher:
            await self.watcher.stop()

        # 배치 큐 플러시
        await self.sync_service.flush_batch_queue()
        logger.info("SyncAgent 중지")


class CentralSyncAgent:
    """NAS 중앙 동기화 에이전트.

    여러 GFX PC의 폴더를 중앙에서 감시하고 동기화합니다.
    Docker 컨테이너에서 실행됩니다.
    """

    def __init__(self, settings: CentralSyncSettings) -> None:
        """초기화.

        Args:
            settings: 중앙 설정
        """
        self.settings = settings
        self.local_queue = LocalQueue(settings.queue_db_path)
        self.sync_service = CentralSyncService(settings, self.local_queue)
        self.watcher: MultiPathWatcher | None = None
        self._running = False
        self._registry_mtime: float = 0

    async def _load_pc_registry(self) -> list[dict[str, Any]]:
        """pc_registry.json에서 PC 목록 로드.

        Returns:
            활성화된 PC 정보 리스트
        """
        registry_path = self.settings.get_registry_full_path()

        if not registry_path.exists():
            logger.warning(f"PC 레지스트리 없음: {registry_path}")
            return []

        try:
            with open(registry_path, encoding="utf-8") as f:
                data = json.load(f)

            self._registry_mtime = registry_path.stat().st_mtime

            pcs = data.get("pcs", [])
            enabled_pcs = [pc for pc in pcs if pc.get("enabled", True)]
            logger.info(f"PC 레지스트리 로드: {len(enabled_pcs)}개 활성화")
            return enabled_pcs
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"PC 레지스트리 로드 실패: {e}")
            return []

    async def start(self) -> None:
        """에이전트 시작."""
        self._running = True
        logger.info("CentralSyncAgent 시작")
        logger.info(f"NAS 기본 경로: {self.settings.nas_base_path}")

        # PC 목록 로드
        pcs = await self._load_pc_registry()
        if not pcs:
            logger.warning("등록된 PC가 없습니다. 대기 중...")

        # MultiPathWatcher 초기화
        self.watcher = MultiPathWatcher(
            base_path=self.settings.nas_base_path,
            on_created=self._handle_created,
            on_modified=self._handle_modified,
            poll_interval=self.settings.poll_interval,
        )

        # 각 PC 폴더 등록
        for pc in pcs:
            self.watcher.add_pc(pc["id"], pc["watch_path"])

        # 기존 파일 초기 동기화 (선택)
        await self._initial_sync(pcs)

        # 병렬 실행: 파일 감시 + 오프라인 큐 처리 + 레지스트리 감시
        loop = asyncio.get_running_loop()
        try:
            await asyncio.gather(
                self.watcher.start(loop),
                self._process_offline_queue_loop(),
                self._watch_registry_changes(),
            )
        except asyncio.CancelledError:
            logger.info("CentralSyncAgent 태스크 취소됨")
            raise

    async def _initial_sync(self, pcs: list[dict[str, Any]]) -> None:
        """기존 파일 초기 동기화.

        Args:
            pcs: PC 정보 리스트
        """
        pc_ids = [pc["id"] for pc in pcs]
        existing_files = await scan_existing_files(
            self.settings.nas_base_path,
            pc_ids,
        )

        total = sum(len(files) for files in existing_files.values())
        if total == 0:
            logger.info("초기 동기화할 파일 없음")
            return

        logger.info(f"초기 동기화 시작: {total}개 파일")

        for pc_id, files in existing_files.items():
            for file_path in files:
                await self.sync_service.sync_file(file_path, "created", pc_id)

        logger.info("초기 동기화 완료")

    async def _handle_created(self, path: str, gfx_pc_id: str) -> None:
        """파일 생성 이벤트 처리.

        Args:
            path: 생성된 파일 경로
            gfx_pc_id: GFX PC 식별자
        """
        await self.sync_service.sync_file(path, "created", gfx_pc_id)

    async def _handle_modified(self, path: str, gfx_pc_id: str) -> None:
        """파일 수정 이벤트 처리.

        Args:
            path: 수정된 파일 경로
            gfx_pc_id: GFX PC 식별자
        """
        await self.sync_service.sync_file(path, "modified", gfx_pc_id)

    async def _process_offline_queue_loop(self) -> None:
        """오프라인 큐 주기적 처리."""
        while self._running:
            try:
                await asyncio.sleep(self.settings.queue_process_interval)
                await self.sync_service.process_offline_queue()
            except asyncio.CancelledError:
                break

    async def _watch_registry_changes(self) -> None:
        """pc_registry.json 변경 감시 (동적 PC 추가/제거)."""
        registry_path = self.settings.get_registry_full_path()

        while self._running:
            try:
                await asyncio.sleep(self.settings.registry_check_interval)

                if not registry_path.exists():
                    continue

                current_mtime = registry_path.stat().st_mtime
                if current_mtime > self._registry_mtime:
                    logger.info("PC 레지스트리 변경 감지, 리로드 중...")
                    await self._reload_pc_registry()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"레지스트리 감시 오류: {e}")

    async def _reload_pc_registry(self) -> None:
        """PC 레지스트리 리로드 및 watcher 업데이트."""
        pcs = await self._load_pc_registry()

        if not self.watcher:
            return

        current_pc_ids = set(self.watcher.get_pc_ids())
        new_pc_ids = {pc["id"] for pc in pcs}

        # 새로 추가된 PC
        for pc in pcs:
            if pc["id"] not in current_pc_ids:
                self.watcher.add_pc(pc["id"], pc["watch_path"])
                logger.info(f"PC 추가됨: {pc['id']}")

        # 제거된 PC
        for pc_id in current_pc_ids - new_pc_ids:
            self.watcher.remove_pc(pc_id)
            logger.info(f"PC 제거됨: {pc_id}")

    async def stop(self) -> None:
        """에이전트 중지."""
        self._running = False

        if self.watcher:
            self.watcher.stop()

        # 배치 큐 플러시
        await self.sync_service.flush_batch_queue()
        logger.info("CentralSyncAgent 중지")


def parse_args() -> argparse.Namespace:
    """CLI 인자 파싱."""
    parser = argparse.ArgumentParser(
        description="GFX JSON → Supabase 동기화 에이전트",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="System Tray 모드로 실행 (Windows GFX PC용)",
    )
    parser.add_argument(
        "--central",
        action="store_true",
        help="NAS 중앙 모드로 실행 (Docker 컨테이너용)",
    )
    return parser.parse_args()


async def run_cli() -> None:
    """CLI 모드 실행 (기존 PC별 방식)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    settings = SyncAgentSettings()
    agent = SyncAgent(settings)

    try:
        await agent.start()
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트 감지")
    finally:
        await agent.stop()


async def run_central() -> None:
    """NAS 중앙 모드 실행 (Docker 컨테이너용)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    settings = CentralSyncSettings()
    agent = CentralSyncAgent(settings)

    logger.info("=" * 60)
    logger.info("GFX Sync Agent - NAS 중앙 모드")
    logger.info("=" * 60)
    logger.info(f"NAS 경로: {settings.nas_base_path}")
    logger.info(f"Supabase URL: {settings.supabase_url[:30]}...")
    logger.info(f"폴링 주기: {settings.poll_interval}초")
    logger.info("=" * 60)

    try:
        await agent.start()
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트 감지")
    finally:
        await agent.stop()


def main() -> None:
    """메인 함수."""
    args = parse_args()

    if args.tray:
        # System Tray 모드 (GUI 설정 사용) - Windows GFX PC용
        from src.sync_agent.tray_app import run_tray_app

        run_tray_app()
    elif args.central:
        # NAS 중앙 모드 (환경 변수 사용) - Docker 컨테이너용
        asyncio.run(run_central())
    else:
        # CLI 모드 (환경 변수 사용) - 기존 PC별 방식
        asyncio.run(run_cli())


if __name__ == "__main__":
    main()
