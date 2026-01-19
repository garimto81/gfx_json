"""Session 모델 정의.

세션/게임 레코드.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


def utcnow() -> datetime:
    """UTC 현재 시간 (timezone-aware)."""
    return datetime.now(UTC)


@dataclass
class SessionRecord:
    """세션 레코드.

    gfx_sessions 테이블에 저장.
    PokerGFX 세션 단위 데이터.

    Attributes:
        id: UUID 기본 키
        session_id: PokerGFX 세션 ID (int64)
        gfx_pc_id: GFX PC 식별자
        file_hash: 파일 SHA256 해시 (중복 방지)
        file_name: 원본 파일명
        event_title: 이벤트 제목
        software_version: PokerGFX 버전
        table_type: 테이블 타입 (FEATURE_TABLE 등)
        created_datetime_utc: 세션 생성 시간 (JSON의 CreatedDateTimeUTC)
        payouts: 페이아웃 배열
        sync_source: 동기화 소스
        hand_count: 핸드 수
        raw_json: 원본 JSON (선택적 보존)
        created_at: 레코드 생성 시간
    """

    session_id: int
    gfx_pc_id: str
    file_hash: str
    file_name: str
    id: UUID = field(default_factory=uuid4)
    event_title: str | None = None
    software_version: str | None = None
    table_type: str | None = None
    created_datetime_utc: datetime | None = None
    payouts: list[int] | None = None
    sync_source: str = "nas_central"
    hand_count: int = 0
    raw_json: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Supabase용 딕셔너리 변환."""
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "gfx_pc_id": self.gfx_pc_id,
            "file_hash": self.file_hash,
            "file_name": self.file_name,
            "event_title": self.event_title,
            "software_version": self.software_version,
            "table_type": self.table_type,
            "created_datetime_utc": (
                self.created_datetime_utc.isoformat() if self.created_datetime_utc else None
            ),
            "payouts": self.payouts,
            "sync_source": self.sync_source,
            "hand_count": self.hand_count,
            "raw_json": self.raw_json,
            "created_at": self.created_at.isoformat(),
        }
