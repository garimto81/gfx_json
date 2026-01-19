"""SQLite 기반 오프라인 큐."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class LocalQueue:
    """SQLite 기반 오프라인 큐.

    네트워크 장애 시 레코드를 로컬에 저장하고
    복구 후 배치 처리합니다.
    """

    def __init__(self, db_path: str) -> None:
        """초기화.

        Args:
            db_path: SQLite DB 파일 경로
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """DB 스키마 초기화."""
        with sqlite3.connect(self.db_path) as conn:
            # 기존 테이블 (하위 호환성)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_sync (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_attempt TIMESTAMP
                )
            """)

            # 새 컬럼 추가 (NAS 중앙 방식용)
            try:
                conn.execute(
                    "ALTER TABLE pending_sync ADD COLUMN gfx_pc_id TEXT DEFAULT 'UNKNOWN'"
                )
            except sqlite3.OperationalError:
                pass  # 컬럼이 이미 존재

            try:
                conn.execute(
                    "ALTER TABLE pending_sync ADD COLUMN error_type TEXT DEFAULT 'network'"
                )
            except sqlite3.OperationalError:
                pass  # 컬럼이 이미 존재

            conn.commit()

    async def enqueue(
        self,
        record: dict[str, Any],
        file_path: str,
        gfx_pc_id: str = "UNKNOWN",
        error_type: str = "network",
    ) -> None:
        """큐에 레코드 추가.

        Args:
            record: 동기화할 레코드 데이터
            file_path: 원본 파일 경로
            gfx_pc_id: GFX PC 식별자 (NAS 중앙 방식)
            error_type: 오류 유형 (network, parse, permission)
        """
        record_json = json.dumps(record, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pending_sync
                (file_path, record_json, gfx_pc_id, error_type)
                VALUES (?, ?, ?, ?)
                """,
                (file_path, record_json, gfx_pc_id, error_type),
            )
            conn.commit()

    async def dequeue_batch(self, limit: int = 50) -> list[dict[str, Any]]:
        """배치 가져오기.

        Args:
            limit: 최대 가져올 레코드 수

        Returns:
            레코드 리스트 (_queue_id, _retry_count, _gfx_pc_id 포함)
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT id, file_path, record_json, retry_count, gfx_pc_id
                FROM pending_sync
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        result = []
        for row in rows:
            record = json.loads(row["record_json"])
            record["_queue_id"] = row["id"]
            record["_file_path"] = row["file_path"]
            record["_retry_count"] = row["retry_count"]
            record["_gfx_pc_id"] = row["gfx_pc_id"] or "UNKNOWN"
            result.append(record)

        return result

    async def mark_completed(self, ids: list[int]) -> None:
        """완료된 레코드 삭제.

        Args:
            ids: 완료된 레코드 ID 리스트
        """
        if not ids:
            return

        placeholders = ",".join("?" * len(ids))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"DELETE FROM pending_sync WHERE id IN ({placeholders})",
                ids,
            )
            conn.commit()

    async def mark_failed(self, queue_id: int) -> None:
        """실패 처리 - retry_count 증가.

        Args:
            queue_id: 실패한 레코드 ID
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE pending_sync
                SET retry_count = retry_count + 1,
                    last_attempt = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (queue_id,),
            )
            conn.commit()

    async def get_pending_count(self) -> int:
        """대기 중인 레코드 수."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pending_sync")
            return cursor.fetchone()[0]

    async def get_stats_by_pc(self) -> list[dict[str, Any]]:
        """PC별 대기 통계.

        Returns:
            PC별 대기 건수, 마지막 오류 시간 등
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT
                    gfx_pc_id,
                    COUNT(*) as pending_count,
                    MAX(created_at) as last_error,
                    error_type
                FROM pending_sync
                GROUP BY gfx_pc_id
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    async def get_stats_by_error_type(self) -> dict[str, int]:
        """오류 유형별 통계.

        Returns:
            오류 유형별 건수
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT error_type, COUNT(*) as count
                FROM pending_sync
                GROUP BY error_type
                """
            )
            return {row[0] or "unknown": row[1] for row in cursor.fetchall()}
