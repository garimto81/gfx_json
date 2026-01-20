"""Hand 모델 정의.

핸드 레코드.
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
class HandRecord:
    """핸드 레코드.

    gfx_hands 테이블에 저장.
    각 핸드의 메타데이터.

    Attributes:
        id: UUID 기본 키
        session_id: 세션 ID (FK)
        hand_num: 핸드 번호
        game_variant: 게임 종류 (HOLDEM, OMAHA 등)
        game_class: 게임 클래스 (FLOP, STUD 등)
        bet_structure: 베팅 구조 (NOLIMIT, POTLIMIT 등)
        duration_seconds: 핸드 진행 시간 (초, INTEGER)
        start_datetime_utc: 핸드 시작 시간 (DB: start_time)
        recording_offset_iso: 녹화 오프셋 ISO 타임스탬프
        recording_offset_seconds: 녹화 오프셋 (초, INTEGER)
        small_blind: 스몰 블라인드
        big_blind: 빅 블라인드
        ante_amt: 앤티 금액 (DB: ante_amt)
        bomb_pot_amt: 폭탄팟 금액
        blinds: JSONB 블라인드 정보 (AEP 매핑용)
        stud_limits: Stud 전용 리밋 (JSONB)
        num_boards: 보드 수
        run_it_num_times: Run It 횟수
        player_count: 참여 플레이어 수
        event_count: 이벤트 수
        pot_size: 최종 팟 크기
        board_cards: 보드 카드 리스트
        winner_name: 승자 이름
        description: 핸드 설명
        created_at: 레코드 생성 시간
    """

    session_id: int
    hand_num: int
    id: UUID = field(default_factory=uuid4)
    game_variant: str = "HOLDEM"
    game_class: str = "FLOP"
    bet_structure: str = "NOLIMIT"
    duration_seconds: int = 0
    start_datetime_utc: datetime | None = None
    recording_offset_iso: str | None = None
    recording_offset_seconds: int | None = None
    small_blind: Decimal | None = None
    big_blind: Decimal | None = None
    ante_amt: Decimal | None = None
    bomb_pot_amt: Decimal | None = None
    blinds: dict[str, Any] | None = None
    stud_limits: dict[str, Any] | None = None
    num_boards: int = 1
    run_it_num_times: int = 1
    player_count: int = 0
    event_count: int = 0
    pot_size: Decimal | None = None
    board_cards: list[str] = field(default_factory=list)
    winner_name: str | None = None
    description: str | None = None
    created_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Supabase용 딕셔너리 변환.

        DB 컬럼명에 맞춰 매핑 (02-GFX-JSON-DB.md 기준).
        - start_datetime_utc → start_time
        - ante_amt → ante_amt (BIGINT)
        - bomb_pot_amt 추가
        """
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "hand_num": self.hand_num,
            "game_variant": self.game_variant,
            "game_class": self.game_class,
            "bet_structure": self.bet_structure,
            "duration_seconds": self.duration_seconds,
            # DB 컬럼명: start_time
            "start_time": (
                self.start_datetime_utc.isoformat() if self.start_datetime_utc else None
            ),
            "recording_offset_iso": self.recording_offset_iso,
            "recording_offset_seconds": self.recording_offset_seconds,
            # small_blind, big_blind는 blinds JSONB 내부에 포함
            # ante_amt, bomb_pot_amt: BIGINT (칩 금액)
            "ante_amt": int(self.ante_amt) if self.ante_amt else 0,
            "bomb_pot_amt": int(self.bomb_pot_amt) if self.bomb_pot_amt else 0,
            "blinds": self.blinds,
            "stud_limits": self.stud_limits,
            "num_boards": self.num_boards,
            "run_it_num_times": self.run_it_num_times,
            "player_count": self.player_count,
            # event_count는 DB에 없음 - 제외
            "pot_size": int(self.pot_size) if self.pot_size else 0,
            "board_cards": self.board_cards,
            "winner_name": self.winner_name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }
