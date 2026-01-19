"""Hand Repository.

gfx_hands 테이블 CRUD.
"""

from __future__ import annotations

import logging

from src.sync_agent.db.supabase_client import SupabaseClient
from src.sync_agent.models.hand import HandRecord
from src.sync_agent.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class HandRepository(BaseRepository[HandRecord]):
    """Hand Repository.

    gfx_hands 테이블 조작.
    (session_id, hand_num) 복합 유니크 기준.
    """

    def __init__(self, client: SupabaseClient) -> None:
        """초기화."""
        super().__init__(client, "gfx_hands")

    async def upsert(self, record: HandRecord) -> HandRecord:
        """(session_id, hand_num) 기준 upsert.

        Args:
            record: HandRecord

        Returns:
            upsert된 레코드
        """
        await self.client.upsert(
            table=self.table,
            records=[record.to_dict()],
            on_conflict="session_id,hand_num",
        )
        return record

    async def upsert_many(self, records: list[HandRecord]) -> int:
        """다건 upsert.

        Args:
            records: HandRecord 리스트

        Returns:
            upsert된 건수
        """
        if not records:
            return 0

        result = await self.client.upsert(
            table=self.table,
            records=[r.to_dict() for r in records],
            on_conflict="session_id,hand_num",
        )
        return result.count

    async def find_by_session(self, session_id: int) -> list[HandRecord]:
        """세션별 핸드 조회.

        Args:
            session_id: 세션 ID

        Returns:
            HandRecord 리스트
        """
        results = await self.client.select(
            table=self.table,
            filters={"session_id": session_id},
        )

        return [self._from_dict(r) for r in results]

    def _from_dict(self, data: dict) -> HandRecord:
        """딕셔너리 → HandRecord 변환."""
        from datetime import datetime
        from decimal import Decimal
        from uuid import UUID

        def parse_dt(v: str | None) -> datetime | None:
            if not v:
                return None
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                return None

        def to_decimal(v) -> Decimal | None:
            if v is None:
                return None
            return Decimal(str(v))

        return HandRecord(
            id=UUID(data["id"]),
            session_id=data["session_id"],
            hand_num=data["hand_num"],
            game_variant=data.get("game_variant", "HOLDEM"),
            game_class=data.get("game_class", "FLOP"),
            bet_structure=data.get("bet_structure", "NOLIMIT"),
            duration_seconds=data.get("duration_seconds", 0.0),
            start_datetime_utc=parse_dt(data.get("start_datetime_utc")),
            recording_offset_start=data.get("recording_offset_start"),
            small_blind=to_decimal(data.get("small_blind")),
            big_blind=to_decimal(data.get("big_blind")),
            ante=to_decimal(data.get("ante")),
            blinds=data.get("blinds"),
            num_boards=data.get("num_boards", 1),
            run_it_num_times=data.get("run_it_num_times", 1),
            player_count=data.get("player_count", 0),
            event_count=data.get("event_count", 0),
            pot_size=to_decimal(data.get("pot_size")),
            board_cards=data.get("board_cards", []),
            winner_name=data.get("winner_name"),
            description=data.get("description"),
            created_at=parse_dt(data.get("created_at")) or datetime.utcnow(),
        )
