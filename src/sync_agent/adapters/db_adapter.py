"""Supabase DB 스키마 Adapter.

코드에서 사용하는 레코드 구조를 실제 Supabase DB 스키마로 변환.

Purpose:
    - 코드 레이어와 DB 레이어 분리
    - 스키마 변경 시 단일 지점에서 관리
    - 실제 DB 필드와 코드 필드 매핑

Schema Mapping:
    - created_datetime_utc → session_created_at
    - gfx_pc_id → gfx_pc_id (동일, Migration 후)
    - sync_source → sync_source (동일, Migration 후)
    - nas_path 자동 생성 (DB 전용 필드)
    - sync_status 기본값 'pending' (DB 전용 필드)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class SupabaseSchemaAdapter:
    """Supabase DB 스키마 변환 Adapter.

    코드 레코드를 실제 Supabase DB 스키마로 변환.

    Examples:
        ```python
        adapter = SupabaseSchemaAdapter()

        code_record = {
            "session_id": 12345,
            "file_hash": "abc...",
            "file_name": "session_12345.json",
            "created_datetime_utc": "2024-01-15T10:00:00Z",
            # ...
        }

        db_record = adapter.to_db_record(code_record, gfx_pc_id="PC01")
        # {
        #     "session_id": 12345,
        #     "gfx_pc_id": "PC01",
        #     "file_hash": "abc...",
        #     "nas_path": "/nas/PC01/session_12345.json",
        #     "session_created_at": "2024-01-15T10:00:00Z",
        #     "sync_status": "pending",
        #     ...
        # }
        ```
    """

    @staticmethod
    def to_db_record(code_record: dict[str, Any], gfx_pc_id: str) -> dict[str, Any]:
        """코드 레코드를 DB 스키마로 변환.

        Args:
            code_record: 코드에서 생성한 레코드
            gfx_pc_id: GFX PC 식별자

        Returns:
            Supabase DB 스키마에 맞춘 레코드

        Field Mapping:
            - created_datetime_utc → session_created_at (DB 필드명)
            - payouts → payouts (DB: integer[], 코드: list[int])
            - raw_json → raw_json (DB: NOT NULL)
            - 추가: nas_path (DB 전용)
            - 추가: sync_status (DB 전용)
        """
        # 기본 필드 매핑
        db_record = {
            # Primary & Unique 필드
            "session_id": code_record["session_id"],
            "file_hash": code_record["file_hash"],
            "file_name": code_record["file_name"],
            # Migration 후 추가된 필드
            "gfx_pc_id": gfx_pc_id,
            "sync_source": code_record.get("sync_source", "nas_central"),
            # DB 전용 필드 (자동 생성)
            "nas_path": f"/nas/{gfx_pc_id}/{code_record['file_name']}",
            "sync_status": "pending",
            # 메타데이터 (필드명 변환)
            "table_type": code_record.get("table_type", "UNKNOWN"),
            "event_title": code_record.get("event_title", ""),
            "software_version": code_record.get("software_version", ""),
            # 시간 필드 매핑
            "session_created_at": code_record.get("created_datetime_utc"),
            # 배열 필드 (DB: integer[], 코드: list[int])
            "payouts": code_record.get("payouts", []),
            # 카운트 필드
            "hand_count": code_record.get("hand_count", 0),
            "player_count": code_record.get("player_count", 0),
            # 원본 JSON (DB: NOT NULL)
            "raw_json": code_record.get("raw_json", {}),
            # 타임스탬프
            "created_at": code_record.get("created_at", datetime.now(UTC).isoformat()),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        return db_record

    @staticmethod
    def from_db_record(db_record: dict[str, Any]) -> dict[str, Any]:
        """DB 레코드를 코드 레코드로 역변환.

        Dashboard나 조회 API에서 사용.

        Args:
            db_record: Supabase DB 레코드

        Returns:
            코드 레이어에서 사용하는 레코드 구조
        """
        # 필드명 역매핑
        code_record = {
            "session_id": db_record["session_id"],
            "gfx_pc_id": db_record["gfx_pc_id"],
            "file_hash": db_record["file_hash"],
            "file_name": db_record["file_name"],
            # 시간 필드 역변환
            "created_datetime_utc": db_record.get("session_created_at"),
            # 메타데이터
            "table_type": db_record.get("table_type"),
            "event_title": db_record.get("event_title"),
            "software_version": db_record.get("software_version"),
            # 배열 필드
            "payouts": db_record.get("payouts", []),
            # 카운트 필드
            "hand_count": db_record.get("hand_count", 0),
            "player_count": db_record.get("player_count", 0),
            # 원본 JSON
            "raw_json": db_record.get("raw_json"),
            # DB 전용 필드 (선택적 포함)
            "sync_source": db_record.get("sync_source"),
            "sync_status": db_record.get("sync_status"),
            "nas_path": db_record.get("nas_path"),
            # 타임스탬프
            "created_at": db_record.get("created_at"),
            "updated_at": db_record.get("updated_at"),
        }

        return code_record

    @staticmethod
    def update_sync_status(
        session_id: int,
        status: str,
        error: str | None = None,
    ) -> dict[str, Any]:
        """sync_status 업데이트용 레코드 생성.

        Args:
            session_id: 세션 ID
            status: 동기화 상태 ('pending', 'success', 'failed')
            error: 오류 메시지 (실패 시)

        Returns:
            UPDATE용 레코드

        Examples:
            ```python
            # 성공 시
            update_data = adapter.update_sync_status(12345, "success")
            # {"sync_status": "success", "processed_at": "...", "sync_error": null}

            # 실패 시
            update_data = adapter.update_sync_status(12345, "failed", "Network error")
            # {"sync_status": "failed", "sync_error": "Network error", "processed_at": "..."}
            ```
        """
        update_data = {
            "sync_status": status,
            "processed_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        if status == "success":
            update_data["sync_error"] = None
        elif status == "failed" and error:
            update_data["sync_error"] = error

        return update_data
