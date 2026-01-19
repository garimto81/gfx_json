"""SyncService v3.0 - NAS 전용 동기화 서비스.

v3.0 설계:
- NAS 전용 (PC 로컬 모드 제거)
- httpx 기반 SupabaseClient 사용
- Settings 단일 클래스 사용
- 지수 백오프 + jitter
"""

from __future__ import annotations

import asyncio
import logging
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from src.sync_agent.config.settings import Settings
from src.sync_agent.core.json_parser import JsonParser
from src.sync_agent.db.supabase_client import RateLimitError, SupabaseClient
from src.sync_agent.queues.batch_queue import BatchQueue
from src.sync_agent.queues.offline_queue import OfflineQueue

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """동기화 결과."""

    success: bool
    error: str | None = None
    pending: bool = False
    queued: bool = False


class SyncService:
    """NAS 전용 동기화 서비스.

    기능:
    - 실시간 동기화 (created → 즉시 upsert)
    - 배치 동기화 (modified → BatchQueue → 배치 upsert)
    - 오프라인 큐 (네트워크 장애 시 SQLite 저장)
    - Rate Limit 대응 (지수 백오프 + jitter)

    Examples:
        ```python
        service = SyncService(
            settings=settings,
            supabase=supabase_client,
            batch_queue=BatchQueue(),
            offline_queue=offline_queue,
        )

        result = await service.sync_file(
            path="/path/to/file.json",
            event_type="created",
            gfx_pc_id="PC01",
        )
        ```
    """

    def __init__(
        self,
        settings: Settings,
        supabase: SupabaseClient,
        batch_queue: BatchQueue,
        offline_queue: OfflineQueue,
        json_parser: JsonParser | None = None,
    ) -> None:
        """초기화.

        Args:
            settings: 설정
            supabase: Supabase 클라이언트
            batch_queue: 배치 큐
            offline_queue: 오프라인 큐
            json_parser: JSON 파서 (선택, 기본 생성)
        """
        self.settings = settings
        self.supabase = supabase
        self.batch_queue = batch_queue
        self.offline_queue = offline_queue
        self.json_parser = json_parser or JsonParser()

    async def sync_file(
        self,
        path: str,
        event_type: Literal["created", "modified"],
        gfx_pc_id: str,
    ) -> SyncResult:
        """파일 동기화.

        Args:
            path: 파일 경로
            event_type: 이벤트 타입
            gfx_pc_id: GFX PC 식별자

        Returns:
            SyncResult
        """
        # JSON 파싱
        parse_result = self.json_parser.parse(path, gfx_pc_id)

        if not parse_result.success:
            if parse_result.error == "file_not_found":
                return SyncResult(success=False, error="file_not_found")

            # 파싱 오류 → 에러 폴더로 이동
            await self._move_to_error_folder(path, gfx_pc_id)
            return SyncResult(success=False, error="parse_error")

        record = parse_result.record
        assert record is not None

        if event_type == "created":
            # 실시간 경로: 즉시 단건 upsert
            return await self._upsert_single(record, path, gfx_pc_id)
        else:
            # 배치 경로: 큐에 추가
            record["_file_path"] = path
            record["_gfx_pc_id"] = gfx_pc_id
            batch = await self.batch_queue.add(record)

            if batch:
                return await self._upsert_batch(batch)

            return SyncResult(success=True, pending=True)

    async def _upsert_single(
        self,
        record: dict[str, Any],
        path: str,
        gfx_pc_id: str,
    ) -> SyncResult:
        """단건 upsert (Rate Limit 대응 포함).

        Args:
            record: 레코드
            path: 원본 파일 경로
            gfx_pc_id: GFX PC 식별자

        Returns:
            SyncResult
        """
        # 내부 메타데이터 제거 (DB 컬럼 없음)
        clean_record = {k: v for k, v in record.items() if not k.startswith("_")}

        for attempt in range(self.settings.rate_limit_max_retries):
            try:
                await self.supabase.upsert(
                    table=self.settings.supabase_table,
                    records=[clean_record],
                    on_conflict="session_id",
                )
                logger.info(f"[{gfx_pc_id}] 동기화 완료: {path}")
                return SyncResult(success=True)

            except RateLimitError:
                wait = self._calculate_backoff(attempt)
                logger.warning(
                    f"[{gfx_pc_id}] Rate Limit, 재시도 {attempt + 1}/{self.settings.rate_limit_max_retries} ({wait:.2f}s)"
                )
                await asyncio.sleep(wait)

            except Exception as e:
                logger.error(
                    f"[{gfx_pc_id}] 동기화 실패, 오프라인 큐에 저장: {path}, {e}"
                )
                await self.offline_queue.enqueue(record, gfx_pc_id, path)
                return SyncResult(success=False, error=str(e), queued=True)

        # 모든 Rate Limit 재시도 실패
        logger.error(f"[{gfx_pc_id}] Rate Limit 재시도 모두 실패: {path}")
        await self.offline_queue.enqueue(record, gfx_pc_id, path)
        return SyncResult(success=False, error="rate_limit_exceeded", queued=True)

    async def _upsert_batch(self, batch: list[dict[str, Any]]) -> SyncResult:
        """배치 upsert.

        Args:
            batch: 레코드 리스트

        Returns:
            SyncResult
        """
        # 내부 메타데이터 분리 (DB 컬럼 없는 필드 제거)
        clean_batch = []
        metadata = []

        for record in batch:
            file_path = record.pop("_file_path", "unknown")
            gfx_pc_id = record.pop("_gfx_pc_id", "UNKNOWN")
            metadata.append({"path": file_path, "pc_id": gfx_pc_id})
            # _ 접두사로 시작하는 모든 내부 필드 제거
            clean_record = {k: v for k, v in record.items() if not k.startswith("_")}
            clean_batch.append(clean_record)

        try:
            await self.supabase.upsert(
                table=self.settings.supabase_table,
                records=clean_batch,
                on_conflict="session_id",
            )
            logger.info(f"배치 동기화 완료: {len(clean_batch)}건")
            return SyncResult(success=True)

        except Exception as e:
            logger.error(f"배치 동기화 실패, 오프라인 큐에 저장: {e}")
            for record, meta in zip(clean_batch, metadata):
                await self.offline_queue.enqueue(record, meta["pc_id"], meta["path"])
            return SyncResult(success=False, error=str(e), queued=True)

    async def flush_batch_queue(self) -> SyncResult | None:
        """배치 큐 강제 플러시.

        Returns:
            SyncResult (플러시 시) 또는 None (빈 큐)
        """
        batch = await self.batch_queue.flush()
        if batch:
            return await self._upsert_batch(batch)
        return None

    async def _move_to_error_folder(self, path: str, gfx_pc_id: str) -> None:
        """오류 파일을 격리 폴더로 이동.

        Args:
            path: 원본 파일 경로
            gfx_pc_id: PC 식별자
        """
        try:
            error_folder = self.settings.full_error_folder
            error_folder.mkdir(parents=True, exist_ok=True)

            src = Path(path)
            if not src.exists():
                return

            dest = error_folder / f"{gfx_pc_id}_{src.name}"
            shutil.move(str(src), str(dest))
            logger.info(f"[{gfx_pc_id}] 오류 파일 격리: {dest}")

        except Exception as e:
            logger.error(f"[{gfx_pc_id}] 파일 이동 실패: {e}")

    def _calculate_backoff(self, attempt: int) -> float:
        """지수 백오프 + jitter 계산.

        Args:
            attempt: 시도 횟수 (0부터 시작)

        Returns:
            대기 시간 (초)
        """
        base = self.settings.rate_limit_base_delay
        backoff = (2**attempt) * base
        jitter = random.uniform(0, 1)
        return backoff + jitter
