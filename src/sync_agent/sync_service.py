"""동기화 서비스."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.sync_agent.batch_queue import BatchQueue
from src.sync_agent.config import CentralSyncSettings, SyncAgentSettings
from src.sync_agent.local_queue import LocalQueue

logger = logging.getLogger(__name__)


class SyncService:
    """GFX JSON → Supabase 동기화 서비스.

    실시간 경로 (Change.added): 즉시 단건 upsert
    배치 경로 (Change.modified): BatchQueue → 배치 upsert
    """

    def __init__(
        self,
        settings: SyncAgentSettings,
        local_queue: LocalQueue,
    ) -> None:
        """초기화.

        Args:
            settings: 설정
            local_queue: 오프라인 큐
        """
        self.settings = settings
        self.local_queue = local_queue
        self.batch_queue = BatchQueue(
            max_size=settings.batch_size,
            flush_interval=settings.flush_interval,
        )
        self._client: Any = None

    def _get_client(self) -> Any:
        """Supabase 클라이언트 (lazy init)."""
        if self._client is None:
            from supabase import create_client

            self._client = create_client(
                self.settings.supabase_url,
                self.settings.get_api_key(),  # 신규 키 우선, 레거시 fallback
            )
        return self._client

    def _parse_json(self, path: str) -> dict[str, Any]:
        """JSON 파일 파싱.

        Args:
            path: 파일 경로

        Returns:
            파싱된 레코드 (file_hash 포함)
        """
        file_path = Path(path)
        content = file_path.read_text(encoding="utf-8")
        data = json.loads(content)

        # file_hash 생성
        file_hash = hashlib.sha256(content.encode()).hexdigest()

        return {
            "file_name": file_path.name,
            "file_hash": file_hash,
            "raw_json": data,
            "session_id": data.get("session_id"),
            "table_type": data.get("table_type"),
            "event_title": data.get("event_title"),
            "software_version": data.get("software_version"),
            "hand_count": data.get("hand_count", 0),
            "sync_source": "gfx_pc_direct",
        }

    async def sync_file(self, path: str, event_type: str) -> None:
        """파일 동기화.

        Args:
            path: 파일 경로
            event_type: 이벤트 타입 ("created" | "modified")
        """
        try:
            record = self._parse_json(path)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"파일 파싱 실패: {path}, {e}")
            return

        if event_type == "created":
            # 실시간 경로: 즉시 단건 upsert
            await self._upsert_single(record, path)
        else:
            # 배치 경로: 큐에 추가
            record["_file_path"] = path
            batch = await self.batch_queue.add(record)
            if batch:
                await self._upsert_batch(batch)

    async def _upsert_single(self, record: dict[str, Any], path: str) -> None:
        """단건 upsert.

        Args:
            record: 레코드
            path: 원본 파일 경로
        """
        try:
            client = self._get_client()
            await client.table("gfx_sessions").upsert(
                record,
                on_conflict="file_hash",
            ).execute()
            logger.info(f"동기화 완료: {path}")
        except Exception as e:
            logger.error(f"동기화 실패, 로컬 큐에 저장: {path}, {e}")
            await self.local_queue.enqueue(record, path)

    async def _upsert_batch(self, batch: list[dict[str, Any]]) -> None:
        """배치 upsert.

        Args:
            batch: 레코드 리스트
        """
        # 내부 메타데이터 제거
        clean_batch = []
        paths = []
        for record in batch:
            paths.append(record.pop("_file_path", "unknown"))
            record.pop("_queue_id", None)
            record.pop("_retry_count", None)
            clean_batch.append(record)

        try:
            client = self._get_client()
            await client.table("gfx_sessions").upsert(
                clean_batch,
                on_conflict="file_hash",
            ).execute()
            logger.info(f"배치 동기화 완료: {len(clean_batch)}건")
        except Exception as e:
            logger.error(f"배치 동기화 실패, 로컬 큐에 저장: {e}")
            for record, path in zip(clean_batch, paths):
                await self.local_queue.enqueue(record, path)

    async def process_offline_queue(self) -> None:
        """오프라인 큐 처리."""
        batch = await self.local_queue.dequeue_batch(limit=50)
        if not batch:
            return

        queue_ids = [r["_queue_id"] for r in batch]
        paths = [r["_file_path"] for r in batch]

        # 메타데이터 제거
        clean_batch = []
        for record in batch:
            record.pop("_queue_id", None)
            record.pop("_file_path", None)
            record.pop("_retry_count", None)
            clean_batch.append(record)

        try:
            client = self._get_client()
            await client.table("gfx_sessions").upsert(
                clean_batch,
                on_conflict="file_hash",
            ).execute()
            await self.local_queue.mark_completed(queue_ids)
            logger.info(f"오프라인 큐 처리 완료: {len(clean_batch)}건")
        except Exception as e:
            logger.error(f"오프라인 큐 처리 실패: {e}")
            for queue_id in queue_ids:
                await self.local_queue.mark_failed(queue_id)

    async def flush_batch_queue(self) -> None:
        """배치 큐 강제 플러시."""
        batch = await self.batch_queue.flush()
        if batch:
            await self._upsert_batch(batch)


class CentralSyncService:
    """NAS 중앙 동기화 서비스.

    여러 GFX PC의 파일을 중앙에서 처리합니다.
    gfx_pc_id를 포함하여 PC별 데이터를 구분합니다.
    """

    def __init__(
        self,
        settings: CentralSyncSettings,
        local_queue: LocalQueue,
    ) -> None:
        """초기화.

        Args:
            settings: 중앙 설정
            local_queue: 오프라인 큐
        """
        self.settings = settings
        self.local_queue = local_queue
        self.batch_queue = BatchQueue(
            max_size=settings.batch_size,
            flush_interval=settings.flush_interval,
        )
        self._client: Any = None

    def _get_client(self) -> Any:
        """Supabase 클라이언트 (lazy init)."""
        if self._client is None:
            from supabase import create_client

            self._client = create_client(
                self.settings.supabase_url,
                self.settings.get_api_key(),  # 신규 키 우선, 레거시 fallback
            )
        return self._client

    def _parse_json(self, path: str, gfx_pc_id: str) -> dict[str, Any]:
        """JSON 파일 파싱 (gfx_pc_id 포함).

        Args:
            path: 파일 경로
            gfx_pc_id: GFX PC 식별자

        Returns:
            파싱된 레코드
        """
        file_path = Path(path)
        content = file_path.read_text(encoding="utf-8")
        data = json.loads(content)

        # file_hash 생성
        file_hash = hashlib.sha256(content.encode()).hexdigest()

        return {
            "gfx_pc_id": gfx_pc_id,  # NAS 중앙 방식 핵심
            "file_name": file_path.name,
            "file_hash": file_hash,
            "raw_json": data,
            "session_id": data.get("session_id"),
            "table_type": data.get("table_type"),
            "event_title": data.get("event_title"),
            "software_version": data.get("software_version"),
            "hand_count": data.get("hand_count", 0),
            "sync_source": "nas_central",  # 출처 구분
        }

    async def sync_file(
        self,
        path: str,
        event_type: str,
        gfx_pc_id: str,
    ) -> None:
        """파일 동기화.

        Args:
            path: 파일 경로
            event_type: 이벤트 타입 ("created" | "modified")
            gfx_pc_id: GFX PC 식별자
        """
        try:
            record = self._parse_json(path, gfx_pc_id)
        except json.JSONDecodeError as e:
            logger.error(f"[{gfx_pc_id}] JSON 파싱 실패: {path}, {e}")
            await self._log_sync_event(gfx_pc_id, "error", 0, f"JSON 파싱 실패: {e}")
            await self._move_to_error_folder(path, gfx_pc_id)
            return
        except OSError as e:
            logger.error(f"[{gfx_pc_id}] 파일 읽기 실패: {path}, {e}")
            await self._log_sync_event(gfx_pc_id, "error", 0, f"파일 읽기 실패: {e}")
            return

        if event_type == "created":
            # 실시간 경로: 즉시 단건 upsert
            await self._upsert_single(record, path, gfx_pc_id)
        else:
            # 배치 경로: 큐에 추가
            record["_file_path"] = path
            record["_gfx_pc_id"] = gfx_pc_id
            batch = await self.batch_queue.add(record)
            if batch:
                await self._upsert_batch(batch)

    async def _upsert_single(
        self,
        record: dict[str, Any],
        path: str,
        gfx_pc_id: str,
    ) -> None:
        """단건 upsert.

        Args:
            record: 레코드
            path: 원본 파일 경로
            gfx_pc_id: GFX PC 식별자
        """
        try:
            client = self._get_client()
            client.table("gfx_sessions").upsert(
                record,
                on_conflict="gfx_pc_id,file_hash",  # 복합 키
            ).execute()
            logger.info(f"[{gfx_pc_id}] 동기화 완료: {path}")
            await self._log_sync_event(gfx_pc_id, "sync", 1)
        except Exception as e:
            logger.error(f"[{gfx_pc_id}] 동기화 실패, 로컬 큐에 저장: {path}, {e}")
            await self._log_sync_event(gfx_pc_id, "error", 0, str(e))
            await self.local_queue.enqueue(record, path, gfx_pc_id, "network")

    async def _upsert_batch(self, batch: list[dict[str, Any]]) -> None:
        """배치 upsert.

        Args:
            batch: 레코드 리스트
        """
        # 내부 메타데이터 제거
        clean_batch = []
        paths = []
        pc_ids = []
        for record in batch:
            paths.append(record.pop("_file_path", "unknown"))
            pc_ids.append(record.pop("_gfx_pc_id", "UNKNOWN"))
            record.pop("_queue_id", None)
            record.pop("_retry_count", None)
            clean_batch.append(record)

        try:
            client = self._get_client()
            client.table("gfx_sessions").upsert(
                clean_batch,
                on_conflict="gfx_pc_id,file_hash",
            ).execute()
            logger.info(f"배치 동기화 완료: {len(clean_batch)}건")

            # PC별 이벤트 로깅
            pc_counts: dict[str, int] = {}
            for pc_id in pc_ids:
                pc_counts[pc_id] = pc_counts.get(pc_id, 0) + 1
            for pc_id, count in pc_counts.items():
                await self._log_sync_event(pc_id, "batch", count)

        except Exception as e:
            logger.error(f"배치 동기화 실패, 로컬 큐에 저장: {e}")
            for record, path, pc_id in zip(clean_batch, paths, pc_ids):
                await self.local_queue.enqueue(record, path, pc_id, "network")

    async def _log_sync_event(
        self,
        gfx_pc_id: str,
        event_type: str,
        file_count: int,
        error_message: str | None = None,
    ) -> None:
        """동기화 이벤트 로깅 (대시보드용).

        Args:
            gfx_pc_id: PC 식별자
            event_type: 이벤트 타입 (sync, error, batch, offline, recovery)
            file_count: 처리 파일 수
            error_message: 오류 메시지 (선택)
        """
        try:
            client = self._get_client()
            client.table("sync_events").insert(
                {
                    "gfx_pc_id": gfx_pc_id,
                    "event_type": event_type,
                    "file_count": file_count,
                    "error_message": error_message,
                    "metadata": {
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                }
            ).execute()
        except Exception as e:
            # 이벤트 로깅 실패는 무시 (핵심 기능 아님)
            logger.debug(f"이벤트 로깅 실패: {e}")

    async def _move_to_error_folder(self, path: str, gfx_pc_id: str) -> None:
        """오류 파일을 격리 폴더로 이동.

        Args:
            path: 원본 파일 경로
            gfx_pc_id: PC 식별자
        """
        try:
            error_folder = self.settings.get_error_folder_path()
            error_folder.mkdir(parents=True, exist_ok=True)

            src = Path(path)
            dest = error_folder / f"{gfx_pc_id}_{src.name}"

            shutil.move(str(src), str(dest))
            logger.info(f"[{gfx_pc_id}] 오류 파일 격리: {dest}")
        except Exception as e:
            logger.error(f"[{gfx_pc_id}] 파일 이동 실패: {e}")

    async def process_offline_queue(self) -> None:
        """오프라인 큐 처리."""
        batch = await self.local_queue.dequeue_batch(limit=50)
        if not batch:
            return

        queue_ids = [r["_queue_id"] for r in batch]
        paths = [r["_file_path"] for r in batch]
        pc_ids = [r.get("_gfx_pc_id", "UNKNOWN") for r in batch]

        # 메타데이터 제거
        clean_batch = []
        for record in batch:
            record.pop("_queue_id", None)
            record.pop("_file_path", None)
            record.pop("_retry_count", None)
            record.pop("_gfx_pc_id", None)
            clean_batch.append(record)

        try:
            client = self._get_client()
            client.table("gfx_sessions").upsert(
                clean_batch,
                on_conflict="gfx_pc_id,file_hash",
            ).execute()
            await self.local_queue.mark_completed(queue_ids)
            logger.info(f"오프라인 큐 처리 완료: {len(clean_batch)}건")

            # 복구 이벤트 로깅
            pc_counts: dict[str, int] = {}
            for pc_id in pc_ids:
                pc_counts[pc_id] = pc_counts.get(pc_id, 0) + 1
            for pc_id, count in pc_counts.items():
                await self._log_sync_event(pc_id, "recovery", count)

        except Exception as e:
            logger.error(f"오프라인 큐 처리 실패: {e}")
            for queue_id in queue_ids:
                await self.local_queue.mark_failed(queue_id)

    async def flush_batch_queue(self) -> None:
        """배치 큐 강제 플러시."""
        batch = await self.batch_queue.flush()
        if batch:
            await self._upsert_batch(batch)
