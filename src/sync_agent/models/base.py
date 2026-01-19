"""Base 모델 정의.

모든 레코드의 기본 클래스.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4


def utcnow() -> datetime:
    """UTC 현재 시간 (timezone-aware)."""
    return datetime.now(UTC)


if TYPE_CHECKING:
    from src.sync_agent.models.event import EventRecord
    from src.sync_agent.models.hand import HandRecord
    from src.sync_agent.models.player import HandPlayerRecord, PlayerRecord
    from src.sync_agent.models.session import SessionRecord


@dataclass
class BaseRecord:
    """모든 레코드의 기본 클래스.

    Attributes:
        id: UUID 기본 키
        created_at: 생성 시간
    """

    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Supabase upsert용 딕셔너리 변환.

        Returns:
            딕셔너리 (UUID는 문자열로, datetime은 ISO 형식으로)
        """
        return {
            "id": str(self.id),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class NormalizedData:
    """정규화된 데이터 컨테이너.

    TransformationPipeline의 출력물.
    UnitOfWork.save_normalized()의 입력물.

    Attributes:
        session: 세션 레코드
        hands: 핸드 레코드 리스트
        players: 플레이어 레코드 리스트 (중복 제거됨)
        hand_players: 핸드-플레이어 연결 레코드 리스트
        events: 이벤트 레코드 리스트
    """

    session: SessionRecord
    hands: list[HandRecord]
    players: list[PlayerRecord]
    hand_players: list[HandPlayerRecord]
    events: list[EventRecord]

    @property
    def stats(self) -> dict[str, int]:
        """레코드 수 통계."""
        return {
            "hands": len(self.hands),
            "players": len(self.players),
            "hand_players": len(self.hand_players),
            "events": len(self.events),
        }
