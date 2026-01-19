"""Event Transformer.

Events[] 항목 → EventRecord 변환.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from src.sync_agent.models.event import EventRecord


class EventTransformer:
    """Event 변환기.

    Events[] 배열의 각 항목을 EventRecord로 변환.

    Examples:
        ```python
        transformer = EventTransformer()
        record = transformer.transform(event_data, hand_id, event_order=0)
        ```
    """

    def transform(
        self,
        data: dict[str, Any],
        hand_id: UUID,
        event_order: int,
    ) -> EventRecord:
        """Events[] 항목 → EventRecord 변환.

        Args:
            data: Events[] 항목
            hand_id: 핸드 UUID
            event_order: 이벤트 순서

        Returns:
            EventRecord
        """
        event_type = data.get("EventType", "UNKNOWN")
        cards = self._parse_board_cards(data.get("BoardCards"))

        return EventRecord(
            hand_id=hand_id,
            event_order=event_order,
            event_type=event_type,
            player_num=data.get("PlayerNum"),
            amount=self._to_decimal(data.get("BetAmt")),
            pot=self._to_decimal(data.get("Pot")),
            cards=cards,
        )

    def validate(self, data: dict[str, Any]) -> list[str]:
        """데이터 검증.

        Args:
            data: Events[] 항목

        Returns:
            에러 메시지 리스트
        """
        errors = []

        if "EventType" not in data:
            errors.append("필수 필드 누락: EventType")

        return errors

    def _parse_board_cards(self, cards: Any) -> list[str]:
        """BoardCards 파싱.

        단일 문자열 또는 배열 처리.

        Args:
            cards: BoardCards 값

        Returns:
            카드 리스트
        """
        if not cards:
            return []

        if isinstance(cards, str):
            return [cards] if cards.strip() else []

        if isinstance(cards, list):
            return [c for c in cards if c and c.strip()]

        return []

    def _to_decimal(self, value: Any) -> Decimal | None:
        """값을 Decimal로 변환."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
