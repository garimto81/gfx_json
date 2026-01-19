"""Session Transformer.

JSON Root → SessionRecord 변환.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.sync_agent.models.session import SessionRecord


class SessionTransformer:
    """Session 변환기.

    JSON Root 객체를 SessionRecord로 변환.

    Examples:
        ```python
        transformer = SessionTransformer()
        record = transformer.transform(json_data, gfx_pc_id="PC01", file_hash="abc")
        ```
    """

    def transform(
        self,
        data: dict[str, Any],
        gfx_pc_id: str,
        file_hash: str,
        file_name: str = "",
    ) -> SessionRecord:
        """JSON Root → SessionRecord 변환.

        Args:
            data: JSON Root 객체
            gfx_pc_id: GFX PC 식별자
            file_hash: 파일 해시
            file_name: 파일명

        Returns:
            SessionRecord
        """
        session_id = data.get("ID", 0)
        created_datetime = self._parse_datetime(data.get("CreatedDateTimeUTC"))
        hand_count = len(data.get("Hands", []))

        return SessionRecord(
            session_id=session_id,
            gfx_pc_id=gfx_pc_id,
            file_hash=file_hash,
            file_name=file_name,
            event_title=data.get("EventTitle"),
            software_version=data.get("SoftwareVersion"),
            table_type=data.get("Type"),
            created_datetime_utc=created_datetime,
            payouts=data.get("Payouts"),
            hand_count=hand_count,
        )

    def validate(self, data: dict[str, Any]) -> list[str]:
        """데이터 검증.

        Args:
            data: JSON Root 객체

        Returns:
            에러 메시지 리스트
        """
        errors = []

        if "ID" not in data:
            errors.append("필수 필드 누락: ID")

        session_id = data.get("ID")
        if session_id is not None and not isinstance(session_id, int):
            errors.append(f"ID는 정수여야 합니다: {type(session_id)}")

        return errors

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """ISO 8601 datetime 파싱.

        Args:
            value: ISO 8601 형식 문자열

        Returns:
            datetime 또는 None
        """
        if not value:
            return None

        try:
            # ISO 8601 형식 (Z suffix 처리)
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except ValueError:
            return None
