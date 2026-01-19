"""Session Repository.

gfx_sessions 테이블 CRUD.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from src.sync_agent.db.supabase_client import SupabaseClient
from src.sync_agent.models.session import SessionRecord
from src.sync_agent.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class SessionRepository(BaseRepository[SessionRecord]):
    """Session Repository.

    gfx_sessions 테이블 조작.
    session_id 기준 upsert.
    """

    def __init__(self, client: SupabaseClient) -> None:
        """초기화."""
        super().__init__(client, "gfx_sessions")

    async def upsert(self, record: SessionRecord) -> SessionRecord:
        """session_id 기준 upsert.

        Args:
            record: SessionRecord

        Returns:
            upsert된 레코드
        """
        await self.client.upsert(
            table=self.table,
            records=[record.to_dict()],
            on_conflict="session_id",
        )
        return record

    async def find_by_session_id(self, session_id: int) -> SessionRecord | None:
        """세션 ID로 조회.

        Args:
            session_id: 세션 ID

        Returns:
            SessionRecord 또는 None
        """
        results = await self.client.select(
            table=self.table,
            filters={"session_id": session_id},
            limit=1,
        )

        if not results:
            return None

        return self._from_dict(results[0])

    async def find_by_file_hash(
        self, gfx_pc_id: str, file_hash: str
    ) -> SessionRecord | None:
        """PC ID + 파일 해시로 조회.

        Args:
            gfx_pc_id: PC ID
            file_hash: 파일 해시

        Returns:
            SessionRecord 또는 None
        """
        results = await self.client.select(
            table=self.table,
            filters={"gfx_pc_id": gfx_pc_id, "file_hash": file_hash},
            limit=1,
        )

        if not results:
            return None

        return self._from_dict(results[0])

    def _from_dict(self, data: dict[str, Any]) -> SessionRecord:
        """딕셔너리 → SessionRecord 변환."""
        from datetime import datetime

        def parse_dt(v: str | None) -> datetime | None:
            if not v:
                return None
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                return None

        return SessionRecord(
            id=UUID(data["id"]),
            session_id=data["session_id"],
            gfx_pc_id=data["gfx_pc_id"],
            file_hash=data["file_hash"],
            file_name=data.get("file_name", ""),
            event_title=data.get("event_title"),
            software_version=data.get("software_version"),
            table_type=data.get("table_type"),
            created_datetime_utc=parse_dt(data.get("created_datetime_utc")),
            payouts=data.get("payouts"),
            sync_source=data.get("sync_source", "nas_central"),
            hand_count=data.get("hand_count", 0),
            raw_json=data.get("raw_json"),
            created_at=parse_dt(data.get("created_at")) or datetime.utcnow(),
        )
