"""Hand Transformer.

Hands[] 항목 → HandRecord 변환.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.sync_agent.models.hand import HandRecord


class HandTransformer:
    """Hand 변환기.

    Hands[] 배열의 각 항목을 HandRecord로 변환.

    Examples:
        ```python
        transformer = HandTransformer()
        record = transformer.transform(hand_data, session_id=12345)
        ```
    """

    # ISO 8601 Duration 정규식 패턴
    DURATION_PATTERN = re.compile(
        r"PT(?:(?P<hours>\d+(?:\.\d+)?)H)?"
        r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
        r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
    )

    def transform(self, data: dict[str, Any], session_id: int) -> HandRecord:
        """Hands[] 항목 → HandRecord 변환.

        Args:
            data: Hands[] 항목
            session_id: 세션 ID

        Returns:
            HandRecord
        """
        blinds_data = data.get("FlopDrawBlinds", {})

        small_blind = self._to_decimal(blinds_data.get("SmallBlindAmt"))
        big_blind = self._to_decimal(blinds_data.get("BigBlindAmt"))
        ante = self._to_decimal(data.get("AnteAmt"))

        # AEP 매핑용 blinds JSONB 생성
        blinds_jsonb = {
            "small_blind_amt": float(small_blind) if small_blind else None,
            "big_blind_amt": float(big_blind) if big_blind else None,
            "ante": float(ante) if ante else None,
        }

        return HandRecord(
            session_id=session_id,
            hand_num=data.get("HandNum", 0),
            game_variant=data.get("GameVariant", "HOLDEM"),
            game_class=data.get("GameClass", "FLOP"),
            bet_structure=data.get("BetStructure", "NOLIMIT"),
            duration_seconds=self.parse_iso_duration(data.get("Duration")),
            start_datetime_utc=self._parse_datetime(data.get("StartDateTimeUTC")),
            recording_offset_seconds=self.parse_iso_duration(
                data.get("RecordingOffsetStart")
            ),
            small_blind=small_blind,
            big_blind=big_blind,
            ante=ante,
            blinds=blinds_jsonb,
            num_boards=data.get("NumBoards", 1),
            run_it_num_times=data.get("RunItNumTimes", 1),
            player_count=len(data.get("Players", [])),
            event_count=len(data.get("Events", [])),
        )

    def validate(self, data: dict[str, Any]) -> list[str]:
        """데이터 검증.

        Args:
            data: Hands[] 항목

        Returns:
            에러 메시지 리스트
        """
        errors = []

        if "HandNum" not in data:
            errors.append("필수 필드 누락: HandNum")

        return errors

    def parse_iso_duration(self, duration: str | None) -> float:
        """ISO 8601 Duration을 초 단위로 변환.

        지원 형식:
        - PT39.2342715S (초만)
        - PT5M30S (분, 초)
        - PT1H30M45S (시, 분, 초)

        Args:
            duration: ISO 8601 Duration 문자열

        Returns:
            초 단위 float
        """
        if not duration:
            return 0.0

        match = self.DURATION_PATTERN.match(duration)
        if not match:
            return 0.0

        hours = float(match.group("hours") or 0)
        minutes = float(match.group("minutes") or 0)
        seconds = float(match.group("seconds") or 0)

        return hours * 3600 + minutes * 60 + seconds

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """ISO 8601 datetime 파싱."""
        if not value:
            return None

        try:
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _to_decimal(self, value: Any) -> Decimal | None:
        """값을 Decimal로 변환."""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
