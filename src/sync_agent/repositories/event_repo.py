"""Event Repository.

gfx_events 테이블 CRUD.
"""

from __future__ import annotations

import logging

from src.sync_agent.db.supabase_client import SupabaseClient
from src.sync_agent.models.event import EventRecord
from src.sync_agent.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class EventRepository(BaseRepository[EventRecord]):
    """Event Repository.

    gfx_events 테이블 조작.
    (hand_id, event_order) 복합 유니크 기준.
    """

    def __init__(self, client: SupabaseClient) -> None:
        """초기화."""
        super().__init__(client, "gfx_events")

    async def upsert(self, record: EventRecord) -> EventRecord:
        """(hand_id, event_order) 기준 upsert.

        Args:
            record: EventRecord

        Returns:
            upsert된 레코드
        """
        await self.client.upsert(
            table=self.table,
            records=[record.to_dict()],
            on_conflict="hand_id,event_order",
        )
        return record

    async def upsert_many(self, records: list[EventRecord]) -> int:
        """다건 upsert.

        Args:
            records: EventRecord 리스트

        Returns:
            upsert된 건수
        """
        if not records:
            return 0

        result = await self.client.upsert(
            table=self.table,
            records=[r.to_dict() for r in records],
            on_conflict="hand_id,event_order",
        )
        return result.count
