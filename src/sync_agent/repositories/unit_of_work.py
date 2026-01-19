"""Unit of Work.

트랜잭션 관리 및 정규화 데이터 저장.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.sync_agent.db.supabase_client import SupabaseClient
from src.sync_agent.models.base import NormalizedData
from src.sync_agent.repositories.event_repo import EventRepository
from src.sync_agent.repositories.hand_player_repo import HandPlayerRepository
from src.sync_agent.repositories.hand_repo import HandRepository
from src.sync_agent.repositories.player_repo import PlayerRepository
from src.sync_agent.repositories.session_repo import SessionRepository

logger = logging.getLogger(__name__)


@dataclass
class SaveResult:
    """저장 결과.

    Attributes:
        success: 성공 여부
        error: 에러 메시지 (실패 시)
        stats: 저장된 건수 통계
    """

    success: bool
    error: str | None = None
    stats: dict[str, int] = field(default_factory=dict)


class UnitOfWork:
    """Unit of Work.

    정규화 데이터 저장 순서 관리.

    저장 순서:
    1. gfx_players (upsert - FK 참조 위해 먼저)
    2. gfx_sessions (upsert)
    3. gfx_hands (create - session FK)
    4. gfx_hand_players (create - hand FK, player FK)
    5. gfx_events (create - hand FK)

    Examples:
        ```python
        uow = UnitOfWork(supabase_client)
        result = await uow.save_normalized(data)

        if result.success:
            print(f"저장 완료: {result.stats}")
        else:
            print(f"실패: {result.error}")
        ```
    """

    def __init__(self, client: SupabaseClient) -> None:
        """초기화.

        Args:
            client: SupabaseClient
        """
        self.client = client
        self.player_repo = PlayerRepository(client)
        self.session_repo = SessionRepository(client)
        self.hand_repo = HandRepository(client)
        self.hand_player_repo = HandPlayerRepository(client)
        self.event_repo = EventRepository(client)

    async def save_normalized(self, data: NormalizedData) -> SaveResult:
        """정규화 데이터 저장.

        순서 보장: Players → Sessions → Hands → HandPlayers → Events

        Args:
            data: NormalizedData

        Returns:
            SaveResult
        """
        stats: dict[str, int] = {}

        try:
            # 1. Players (FK 참조 위해 먼저)
            player_count = await self.player_repo.upsert_many(data.players)
            stats["players"] = player_count
            logger.debug(f"Players 저장: {player_count}건")

            # 2. Session
            await self.session_repo.upsert(data.session)
            stats["sessions"] = 1
            logger.debug(f"Session 저장: {data.session.session_id}")

            # 3. Hands
            hand_count = await self.hand_repo.upsert_many(data.hands)
            stats["hands"] = hand_count
            logger.debug(f"Hands 저장: {hand_count}건")

            # 4. HandPlayers
            hp_count = await self.hand_player_repo.upsert_many(data.hand_players)
            stats["hand_players"] = hp_count
            logger.debug(f"HandPlayers 저장: {hp_count}건")

            # 5. Events
            event_count = await self.event_repo.upsert_many(data.events)
            stats["events"] = event_count
            logger.debug(f"Events 저장: {event_count}건")

            logger.info(
                f"정규화 데이터 저장 완료: session={data.session.session_id}, "
                f"hands={hand_count}, players={player_count}, events={event_count}"
            )

            return SaveResult(success=True, stats=stats)

        except Exception as e:
            logger.error(f"정규화 데이터 저장 실패: {e}")
            return SaveResult(success=False, error=str(e), stats=stats)
