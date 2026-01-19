"""Player Repository.

gfx_players 테이블 CRUD.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.sync_agent.db.supabase_client import SupabaseClient
from src.sync_agent.models.player import PlayerRecord
from src.sync_agent.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class PlayerRepository(BaseRepository[PlayerRecord]):
    """Player Repository.

    gfx_players 테이블 조작.
    player_hash 기준 upsert.
    """

    def __init__(self, client: SupabaseClient) -> None:
        """초기화."""
        super().__init__(client, "gfx_players")

    async def upsert(self, record: PlayerRecord) -> PlayerRecord:
        """player_hash 기준 upsert.

        Args:
            record: PlayerRecord

        Returns:
            upsert된 레코드
        """
        await self.client.upsert(
            table=self.table,
            records=[record.to_dict()],
            on_conflict="player_hash",
        )
        return record

    async def upsert_many(self, records: list[PlayerRecord]) -> int:
        """다건 upsert.

        last_seen_at 업데이트.

        Args:
            records: PlayerRecord 리스트

        Returns:
            upsert된 건수
        """
        if not records:
            return 0

        dicts = []
        now = datetime.now(UTC).isoformat()

        for r in records:
            d = r.to_dict()
            d["last_seen_at"] = now
            dicts.append(d)

        result = await self.client.upsert(
            table=self.table,
            records=dicts,
            on_conflict="player_hash",
        )
        return result.count

    async def find_by_hash(self, player_hash: str) -> PlayerRecord | None:
        """해시로 조회.

        Args:
            player_hash: 플레이어 해시

        Returns:
            PlayerRecord 또는 None
        """
        results = await self.client.select(
            table=self.table,
            filters={"player_hash": player_hash},
            limit=1,
        )

        if not results:
            return None

        return self._from_dict(results[0])

    async def find_by_id(self, player_id: UUID) -> PlayerRecord | None:
        """ID로 조회.

        Args:
            player_id: 플레이어 UUID

        Returns:
            PlayerRecord 또는 None
        """
        results = await self.client.select(
            table=self.table,
            filters={"id": str(player_id)},
            limit=1,
        )

        if not results:
            return None

        return self._from_dict(results[0])

    def _from_dict(self, data: dict[str, Any]) -> PlayerRecord:
        """딕셔너리 → PlayerRecord 변환.

        Args:
            data: 딕셔너리

        Returns:
            PlayerRecord
        """
        from datetime import datetime

        def parse_dt(v: str | None) -> datetime:
            if not v:
                return datetime.now(UTC)
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                return datetime.now(UTC)

        return PlayerRecord(
            id=UUID(data["id"]),
            player_hash=data["player_hash"],
            name=data["name"],
            long_name=data.get("long_name"),
            first_seen_at=parse_dt(data.get("first_seen_at")),
            last_seen_at=parse_dt(data.get("last_seen_at")),
            total_hands=data.get("total_hands", 0),
            created_at=parse_dt(data.get("created_at")),
        )
