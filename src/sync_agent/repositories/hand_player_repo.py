"""HandPlayer Repository.

gfx_hand_players 테이블 CRUD.
"""

from __future__ import annotations

import logging

from src.sync_agent.db.supabase_client import SupabaseClient
from src.sync_agent.models.player import HandPlayerRecord
from src.sync_agent.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class HandPlayerRepository(BaseRepository[HandPlayerRecord]):
    """HandPlayer Repository.

    gfx_hand_players 테이블 조작.
    (hand_id, seat_num) 복합 유니크 기준.
    """

    def __init__(self, client: SupabaseClient) -> None:
        """초기화."""
        super().__init__(client, "gfx_hand_players")

    async def upsert(self, record: HandPlayerRecord) -> HandPlayerRecord:
        """(hand_id, seat_num) 기준 upsert.

        Args:
            record: HandPlayerRecord

        Returns:
            upsert된 레코드
        """
        await self.client.upsert(
            table=self.table,
            records=[record.to_dict()],
            on_conflict="hand_id,seat_num",
        )
        return record

    async def upsert_many(self, records: list[HandPlayerRecord]) -> int:
        """다건 upsert.

        Args:
            records: HandPlayerRecord 리스트

        Returns:
            upsert된 건수
        """
        if not records:
            return 0

        result = await self.client.upsert(
            table=self.table,
            records=[r.to_dict() for r in records],
            on_conflict="hand_id,seat_num",
        )
        return result.count
