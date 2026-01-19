"""오프라인 큐 모듈.

aiosqlite 기반 비동기 영속 큐.
Dead Letter Queue 포함.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class QueuedRecord:
    """큐에 저장된 레코드."""

    id: int
    record: dict[str, Any]
    gfx_pc_id: str
    file_path: str | None
    retry_count: int
    created_at: str
    last_error: str | None


@dataclass
class DeadLetterRecord:
    """Dead Letter Queue 레코드."""

    id: int
    record: dict[str, Any]
    gfx_pc_id: str
    file_path: str | None
    retry_count: int
    error_reason: str
    created_at: str


class OfflineQueue:
    """aiosqlite 기반 오프라인 큐.

    기능:
    - 비동기 I/O (aiosqlite)
    - WAL 모드 (동시성 향상)
    - Dead Letter Queue (영구 실패 레코드 격리)
    - 큐 크기 제한
    - 재시도 카운트 관리

    Examples:
        ```python
        queue = OfflineQueue("/app/queue/pending.db", max_size=10000)
        await queue.connect()

        # 레코드 추가
        queue_id = await queue.enqueue(record, "PC01", "/path/to/file.json")

        # 배치 조회
        records = await queue.dequeue_batch(limit=50)

        # 성공/실패 처리
        await queue.mark_completed([1, 2, 3])
        await queue.mark_failed(4, "Connection timeout")

        await queue.close()
        ```
    """

    def __init__(
        self,
        db_path: str,
        max_size: int = 10000,
        max_retries: int = 5,
    ) -> None:
        """초기화.

        Args:
            db_path: SQLite DB 파일 경로
            max_size: 큐 최대 크기 (초과 시 가장 오래된 레코드 제거)
            max_retries: 최대 재시도 횟수 (초과 시 Dead Letter Queue로 이동)
        """
        self.db_path = db_path
        self.max_size = max_size
        self.max_retries = max_retries
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """DB 연결 및 초기화."""
        # 디렉토리 생성
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        # WAL 모드 설정 (동시 읽기/쓰기 성능 향상)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA busy_timeout=5000")

        await self._init_tables()
        logger.info(f"OfflineQueue 연결: {self.db_path}")

    async def _init_tables(self) -> None:
        """테이블 초기화."""
        # 메인 큐 테이블
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS pending_sync (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_json TEXT NOT NULL,
                gfx_pc_id TEXT NOT NULL,
                file_path TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_error TEXT
            )
        """)

        # Dead Letter Queue 테이블
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS dead_letter (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_json TEXT NOT NULL,
                gfx_pc_id TEXT NOT NULL,
                file_path TEXT,
                retry_count INTEGER,
                error_reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 인덱스 생성
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_retry ON pending_sync(retry_count)"
        )
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_pc ON pending_sync(gfx_pc_id)"
        )

        await self._db.commit()

    async def close(self) -> None:
        """DB 연결 종료."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("OfflineQueue 연결 종료")

    async def enqueue(
        self,
        record: dict[str, Any],
        gfx_pc_id: str,
        file_path: str | None = None,
    ) -> int:
        """레코드를 큐에 추가.

        Args:
            record: 동기화할 레코드 (JSON 직렬화 가능)
            gfx_pc_id: GFX PC 식별자
            file_path: 원본 파일 경로 (선택)

        Returns:
            큐 ID

        Raises:
            RuntimeError: DB 미연결 시
        """
        self._ensure_connected()

        # 큐 크기 확인 및 정리
        current_size = await self.count()
        if current_size >= self.max_size:
            removed = await self._remove_oldest(count=max(1, current_size - self.max_size + 1))
            logger.warning(f"큐 크기 초과로 {removed}건 제거 (현재: {current_size})")

        cursor = await self._db.execute(
            """
            INSERT INTO pending_sync (record_json, gfx_pc_id, file_path)
            VALUES (?, ?, ?)
            """,
            (json.dumps(record, ensure_ascii=False), gfx_pc_id, file_path),
        )
        await self._db.commit()

        queue_id = cursor.lastrowid
        logger.debug(f"큐 추가: id={queue_id}, pc={gfx_pc_id}")
        return queue_id

    async def dequeue_batch(self, limit: int = 50) -> list[QueuedRecord]:
        """배치 조회 (재시도 횟수 적은 순서).

        Args:
            limit: 최대 조회 개수

        Returns:
            큐 레코드 리스트
        """
        self._ensure_connected()

        async with self._db.execute(
            """
            SELECT id, record_json, gfx_pc_id, file_path, retry_count, created_at, last_error
            FROM pending_sync
            ORDER BY retry_count ASC, id ASC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            QueuedRecord(
                id=row["id"],
                record=json.loads(row["record_json"]),
                gfx_pc_id=row["gfx_pc_id"],
                file_path=row["file_path"],
                retry_count=row["retry_count"],
                created_at=row["created_at"],
                last_error=row["last_error"],
            )
            for row in rows
        ]

    async def mark_completed(self, queue_ids: list[int]) -> int:
        """성공 처리 (큐에서 제거).

        Args:
            queue_ids: 완료된 큐 ID 목록

        Returns:
            삭제된 건수
        """
        self._ensure_connected()

        if not queue_ids:
            return 0

        placeholders = ",".join("?" * len(queue_ids))
        cursor = await self._db.execute(
            f"DELETE FROM pending_sync WHERE id IN ({placeholders})",
            queue_ids,
        )
        await self._db.commit()

        deleted = cursor.rowcount
        logger.debug(f"큐 완료 처리: {deleted}건")
        return deleted

    async def mark_failed(self, queue_id: int, error: str) -> bool:
        """실패 처리.

        재시도 횟수가 max_retries 이상이면 Dead Letter Queue로 이동.

        Args:
            queue_id: 큐 ID
            error: 오류 메시지

        Returns:
            Dead Letter Queue로 이동했으면 True
        """
        self._ensure_connected()

        # 현재 레코드 조회
        async with self._db.execute(
            """
            SELECT id, record_json, gfx_pc_id, file_path, retry_count
            FROM pending_sync WHERE id = ?
            """,
            (queue_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            logger.warning(f"큐 레코드 없음: id={queue_id}")
            return False

        current_retry = row["retry_count"]

        if current_retry >= self.max_retries - 1:
            # Dead Letter Queue로 이동
            await self._db.execute(
                """
                INSERT INTO dead_letter (record_json, gfx_pc_id, file_path, retry_count, error_reason)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["record_json"],
                    row["gfx_pc_id"],
                    row["file_path"],
                    current_retry + 1,
                    error,
                ),
            )
            await self._db.execute("DELETE FROM pending_sync WHERE id = ?", (queue_id,))
            await self._db.commit()

            logger.warning(
                f"Dead Letter Queue 이동: id={queue_id}, pc={row['gfx_pc_id']}, error={error}"
            )
            return True
        else:
            # 재시도 카운트 증가
            await self._db.execute(
                """
                UPDATE pending_sync
                SET retry_count = retry_count + 1, last_error = ?
                WHERE id = ?
                """,
                (error, queue_id),
            )
            await self._db.commit()

            logger.debug(f"재시도 예약: id={queue_id}, retry={current_retry + 1}")
            return False

    async def count(self) -> int:
        """대기 중인 레코드 수."""
        self._ensure_connected()

        async with self._db.execute("SELECT COUNT(*) FROM pending_sync") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def dead_letter_count(self) -> int:
        """Dead Letter Queue 레코드 수."""
        self._ensure_connected()

        async with self._db.execute("SELECT COUNT(*) FROM dead_letter") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_dead_letters(self, limit: int = 100) -> list[DeadLetterRecord]:
        """Dead Letter Queue 조회.

        Args:
            limit: 최대 조회 개수

        Returns:
            Dead Letter 레코드 리스트
        """
        self._ensure_connected()

        async with self._db.execute(
            """
            SELECT id, record_json, gfx_pc_id, file_path, retry_count, error_reason, created_at
            FROM dead_letter
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            DeadLetterRecord(
                id=row["id"],
                record=json.loads(row["record_json"]),
                gfx_pc_id=row["gfx_pc_id"],
                file_path=row["file_path"],
                retry_count=row["retry_count"],
                error_reason=row["error_reason"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def retry_dead_letter(self, dead_letter_id: int) -> int | None:
        """Dead Letter 레코드 재시도 (메인 큐로 복원).

        Args:
            dead_letter_id: Dead Letter 레코드 ID

        Returns:
            새 큐 ID (성공 시), None (실패 시)
        """
        self._ensure_connected()

        async with self._db.execute(
            "SELECT record_json, gfx_pc_id, file_path FROM dead_letter WHERE id = ?",
            (dead_letter_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        # 메인 큐로 복원 (retry_count 0으로 리셋)
        cursor = await self._db.execute(
            """
            INSERT INTO pending_sync (record_json, gfx_pc_id, file_path, retry_count)
            VALUES (?, ?, ?, 0)
            """,
            (row["record_json"], row["gfx_pc_id"], row["file_path"]),
        )

        # Dead Letter에서 삭제
        await self._db.execute("DELETE FROM dead_letter WHERE id = ?", (dead_letter_id,))
        await self._db.commit()

        new_id = cursor.lastrowid
        logger.info(f"Dead Letter 재시도: dl_id={dead_letter_id} -> queue_id={new_id}")
        return new_id

    async def get_stats(self) -> dict[str, Any]:
        """큐 통계 조회."""
        self._ensure_connected()

        pending = await self.count()
        dead_letter = await self.dead_letter_count()

        # PC별 통계
        async with self._db.execute(
            """
            SELECT gfx_pc_id, COUNT(*) as count, MAX(retry_count) as max_retry
            FROM pending_sync
            GROUP BY gfx_pc_id
            """
        ) as cursor:
            pc_stats = {row["gfx_pc_id"]: {"count": row["count"], "max_retry": row["max_retry"]} for row in await cursor.fetchall()}

        return {
            "pending_count": pending,
            "dead_letter_count": dead_letter,
            "max_size": self.max_size,
            "max_retries": self.max_retries,
            "utilization": pending / self.max_size if self.max_size > 0 else 0,
            "by_pc": pc_stats,
        }

    async def _remove_oldest(self, count: int = 1) -> int:
        """가장 오래된 레코드 제거.

        Args:
            count: 제거할 개수

        Returns:
            실제 제거된 건수
        """
        cursor = await self._db.execute(
            """
            DELETE FROM pending_sync
            WHERE id IN (
                SELECT id FROM pending_sync
                ORDER BY created_at ASC
                LIMIT ?
            )
            """,
            (count,),
        )
        await self._db.commit()
        return cursor.rowcount

    def _ensure_connected(self) -> None:
        """연결 상태 확인."""
        if self._db is None:
            raise RuntimeError("OfflineQueue가 연결되지 않음. connect() 먼저 호출하세요.")

    async def __aenter__(self) -> "OfflineQueue":
        """async with 지원."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """async with 종료."""
        await self.close()
