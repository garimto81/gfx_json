"""Player Transformer.

Players[] 항목 → PlayerRecord, HandPlayerRecord 변환.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from src.sync_agent.models.player import HandPlayerRecord, PlayerRecord


class PlayerTransformer:
    """Player 변환기.

    Players[] 배열의 각 항목을 PlayerRecord와 HandPlayerRecord로 변환.

    Examples:
        ```python
        transformer = PlayerTransformer()

        # 마스터 플레이어 레코드
        player = transformer.transform(player_data)

        # 핸드별 플레이어 레코드
        hand_player = transformer.transform_for_hand(player_data, hand_id, player_id)
        ```
    """

    def transform(self, data: dict[str, Any]) -> PlayerRecord:
        """Players[] 항목 → PlayerRecord 변환.

        Args:
            data: Players[] 항목

        Returns:
            PlayerRecord (마스터)
        """
        name = data.get("Name", "")
        long_name = data.get("LongName")

        return PlayerRecord.create(name=name, long_name=long_name)

    def transform_for_hand(
        self,
        data: dict[str, Any],
        hand_id: UUID,
        player_id: UUID,
    ) -> HandPlayerRecord:
        """Players[] 항목 → HandPlayerRecord 변환.

        Args:
            data: Players[] 항목
            hand_id: 핸드 UUID
            player_id: 플레이어 UUID

        Returns:
            HandPlayerRecord
        """
        hole_cards = self.parse_hole_cards(data.get("HoleCards", []))
        return HandPlayerRecord(
            hand_id=hand_id,
            player_id=player_id,
            seat_num=data.get("PlayerNum", 0),
            player_name=data.get("Name"),
            hole_cards=hole_cards,
            has_shown=len(hole_cards) > 0,
            start_stack_amt=self._to_decimal(data.get("StartStackAmt")),
            end_stack_amt=self._to_decimal(data.get("EndStackAmt")),
            cumulative_winnings_amt=self._to_decimal(data.get("CumulativeWinningsAmt")),
            blind_bet_straddle_amt=data.get("BlindBetStraddleAmt", 0) or 0,
            vpip_percent=data.get("VPIPPercent"),
            preflop_raise_percent=data.get("PreflopRaisePercent"),
            aggression_frequency_percent=data.get("AggressionFrequencyPercent"),
            went_to_showdown_percent=data.get("WentToShowDownPercent"),
            sitting_out=data.get("SittingOut", False),
            is_winner=data.get("IsWinner", False),
            elimination_rank=data.get("EliminationRank", -1) if data.get("EliminationRank") else -1,
        )

    def validate(self, data: dict[str, Any]) -> list[str]:
        """데이터 검증.

        Args:
            data: Players[] 항목

        Returns:
            에러 메시지 리스트
        """
        errors = []

        if "Name" not in data and "PlayerNum" not in data:
            errors.append("Name 또는 PlayerNum 필요")

        return errors

    def parse_hole_cards(self, cards: list[str] | None) -> list[str]:
        """HoleCards 파싱.

        빈 문자열 필터링, 공백으로 구분된 카드 분리.

        Args:
            cards: HoleCards 배열

        Returns:
            정제된 카드 리스트
        """
        if not cards:
            return []

        result = []
        for card in cards:
            if not card or card.strip() == "":
                continue
            # 공백으로 구분된 경우 분리 (예: "As Kh")
            if " " in card:
                result.extend(card.split())
            else:
                result.append(card)

        return result

    def _to_decimal(self, value: Any) -> Decimal | None:
        """값을 Decimal로 변환."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
