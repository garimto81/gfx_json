"""Player 모델 정의.

플레이어 마스터 및 핸드별 플레이어 레코드.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4


def utcnow() -> datetime:
    """UTC 현재 시간 (timezone-aware)."""
    return datetime.now(UTC)


@dataclass
class PlayerRecord:
    """플레이어 마스터 레코드.

    gfx_players 테이블에 저장.
    player_hash로 중복 방지.

    Attributes:
        id: UUID 기본 키
        player_hash: MD5(name:long_name) - 중복 방지용
        name: 플레이어 단축명
        long_name: 플레이어 전체명 (선택)
        first_seen_at: 최초 등장 시간
        last_seen_at: 마지막 등장 시간
        total_hands: 총 참여 핸드 수
        created_at: 레코드 생성 시간
    """

    name: str
    long_name: str | None = None
    player_hash: str = ""
    id: UUID = field(default_factory=uuid4)
    first_seen_at: datetime = field(default_factory=utcnow)
    last_seen_at: datetime = field(default_factory=utcnow)
    total_hands: int = 0
    created_at: datetime = field(default_factory=utcnow)

    @staticmethod
    def generate_hash(name: str, long_name: str | None) -> str:
        """player_hash 생성.

        Args:
            name: 플레이어 이름
            long_name: 플레이어 전체명 (None 허용)

        Returns:
            MD5 해시 (32자)
        """
        content = f"{name}:{long_name or ''}"
        return hashlib.md5(content.encode()).hexdigest()

    @classmethod
    def create(cls, name: str, long_name: str | None = None) -> "PlayerRecord":
        """자동 해시 생성으로 PlayerRecord 생성.

        Args:
            name: 플레이어 이름
            long_name: 플레이어 전체명

        Returns:
            PlayerRecord 인스턴스
        """
        return cls(
            name=name,
            long_name=long_name,
            player_hash=cls.generate_hash(name, long_name),
        )

    def to_dict(self) -> dict[str, Any]:
        """Supabase용 딕셔너리 변환."""
        return {
            "id": str(self.id),
            "player_hash": self.player_hash,
            "name": self.name,
            "long_name": self.long_name,
            "first_seen_at": self.first_seen_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "total_hands": self.total_hands,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class HandPlayerRecord:
    """핸드별 플레이어 레코드.

    gfx_hand_players 테이블에 저장.
    각 핸드에서의 플레이어 상태를 기록.

    Attributes:
        id: UUID 기본 키
        hand_id: 핸드 FK
        player_id: 플레이어 FK
        seat_num: 좌석 번호 (1-10)
        player_name: 플레이어명 (비정규화, AEP 매핑용)
        hole_cards: 홀 카드 (예: ["As", "Kh"])
        has_shown: 카드 공개 여부
        start_stack_amt: 시작 스택
        end_stack_amt: 종료 스택
        cumulative_winnings_amt: 누적 수익
        blind_bet_straddle_amt: 블라인드/스트래들 금액
        vpip_percent: VPIP%
        preflop_raise_percent: PFR%
        aggression_frequency_percent: Aggression%
        went_to_showdown_percent: 쇼다운 진출률%
        sitting_out: 자리 비움 여부
        is_winner: 승자 여부
        elimination_rank: 탈락 순위 (-1 = 미탈락)
        created_at: 레코드 생성 시간
    """

    hand_id: UUID
    player_id: UUID
    seat_num: int = 0
    id: UUID = field(default_factory=uuid4)
    player_name: str | None = None
    hole_cards: list[str] = field(default_factory=list)
    has_shown: bool = False
    start_stack_amt: Decimal | None = None
    end_stack_amt: Decimal | None = None
    cumulative_winnings_amt: Decimal | None = None
    blind_bet_straddle_amt: int = 0
    vpip_percent: float | None = None
    preflop_raise_percent: float | None = None
    aggression_frequency_percent: float | None = None
    went_to_showdown_percent: float | None = None
    sitting_out: bool = False
    is_winner: bool = False
    elimination_rank: int = -1
    created_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Supabase용 딕셔너리 변환."""
        return {
            "id": str(self.id),
            "hand_id": str(self.hand_id),
            "player_id": str(self.player_id),
            "seat_num": self.seat_num,
            "player_name": self.player_name,
            "hole_cards": self.hole_cards,
            "has_shown": self.has_shown,
            "start_stack_amt": float(self.start_stack_amt) if self.start_stack_amt else None,
            "end_stack_amt": float(self.end_stack_amt) if self.end_stack_amt else None,
            "cumulative_winnings_amt": (
                float(self.cumulative_winnings_amt) if self.cumulative_winnings_amt else None
            ),
            "blind_bet_straddle_amt": self.blind_bet_straddle_amt,
            "vpip_percent": self.vpip_percent,
            "preflop_raise_percent": self.preflop_raise_percent,
            "aggression_frequency_percent": self.aggression_frequency_percent,
            "went_to_showdown_percent": self.went_to_showdown_percent,
            "sitting_out": self.sitting_out,
            "is_winner": self.is_winner,
            "elimination_rank": self.elimination_rank,
            "created_at": self.created_at.isoformat(),
        }
