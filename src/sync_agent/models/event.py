"""Event 모델 정의.

이벤트/액션 레코드.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4


def utcnow() -> datetime:
    """UTC 현재 시간 (timezone-aware)."""
    return datetime.now(UTC)


@dataclass
class EventRecord:
    """이벤트 레코드.

    gfx_events 테이블에 저장.
    핸드 내 액션/이벤트 시퀀스.

    Attributes:
        id: UUID 기본 키
        hand_id: 핸드 FK
        event_order: 이벤트 순서 (핸드 내)
        event_type: 이벤트 타입 (FOLD, BET, CALL, CHECK, RAISE, ALL_IN, BOARD_CARD 등)
        player_num: 플레이어 좌석 번호 (액션 이벤트 시)
        amount: 베팅 금액 (베팅 이벤트 시)
        cards: 보드 카드 (BOARD_CARD 이벤트 시)
        pot: 현재 팟 크기
        event_time: 이벤트 발생 시간 (ISO 8601)
        extra_data: 추가 데이터 (JSONB)
        created_at: 레코드 생성 시간
    """

    hand_id: UUID
    event_order: int
    event_type: str
    id: UUID = field(default_factory=uuid4)
    player_num: int | None = None
    amount: Decimal | None = None
    cards: list[str] = field(default_factory=list)
    pot: Decimal | None = None
    event_time: str | None = None
    extra_data: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Supabase용 딕셔너리 변환."""
        return {
            "id": str(self.id),
            "hand_id": str(self.hand_id),
            "event_order": self.event_order,
            "event_type": self.event_type,
            "player_num": self.player_num,
            "amount": float(self.amount) if self.amount else None,
            "cards": self.cards if self.cards else None,
            "pot": float(self.pot) if self.pot else None,
            "event_time": self.event_time,
            "extra_data": self.extra_data,
            "created_at": self.created_at.isoformat(),
        }
