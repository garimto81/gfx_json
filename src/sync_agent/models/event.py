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
        player_num: 플레이어 좌석 번호 (액션 이벤트 시, 0 = 보드)
        bet_amt: 베팅 금액 (베팅 이벤트 시)
        pot: 현재 팟 크기
        board_cards: 보드 카드 (BOARD_CARD 이벤트 시, 단일 카드 문자열)
        board_num: 보드 번호 (Run it twice 시 사용)
        num_cards_drawn: Draw 게임용 드로우 카드 수
        event_time: 이벤트 발생 시간 (ISO 8601)
        created_at: 레코드 생성 시간
    """

    hand_id: UUID
    event_order: int
    event_type: str
    id: UUID = field(default_factory=uuid4)
    player_num: int | None = None
    bet_amt: Decimal | None = None
    pot: Decimal | None = None
    board_cards: list[str] = field(default_factory=list)
    board_num: int = 0
    num_cards_drawn: int = 0
    event_time: str | None = None
    created_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Supabase용 딕셔너리 변환.

        DB 컬럼명에 맞춰 매핑 (02-GFX-JSON-DB.md 기준).
        """
        # board_cards: 단일 카드 문자열로 변환 (DB는 TEXT, 배열 아님)
        board_cards_str = self.board_cards[0] if self.board_cards else None
        return {
            "id": str(self.id),
            "hand_id": str(self.hand_id),
            "event_order": self.event_order,
            "event_type": self.event_type,
            "player_num": self.player_num,
            "bet_amt": float(self.bet_amt) if self.bet_amt else None,
            "pot": float(self.pot) if self.pot else None,
            "board_cards": board_cards_str,
            "board_num": self.board_num,
            "num_cards_drawn": self.num_cards_drawn,
            "event_time": self.event_time,
            "created_at": self.created_at.isoformat(),
        }
