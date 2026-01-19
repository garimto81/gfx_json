"""Base Repository 정의.

Repository 패턴 기본 클래스.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from src.sync_agent.db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """Repository 기본 클래스.

    모든 Repository가 상속하는 추상 클래스.
    공통 CRUD 메서드 제공.

    Attributes:
        client: SupabaseClient 인스턴스
        table: 테이블명
    """

    def __init__(self, client: SupabaseClient, table: str) -> None:
        """초기화.

        Args:
            client: SupabaseClient
            table: 테이블명
        """
        self.client = client
        self.table = table

    async def create(self, record: T) -> T:
        """단건 생성.

        Args:
            record: 레코드

        Returns:
            생성된 레코드
        """
        await self.client.upsert(
            table=self.table,
            records=[self._to_dict(record)],
            on_conflict="id",
        )
        return record

    async def create_many(self, records: list[T]) -> int:
        """다건 생성.

        Args:
            records: 레코드 리스트

        Returns:
            생성된 건수
        """
        if not records:
            return 0

        result = await self.client.upsert(
            table=self.table,
            records=[self._to_dict(r) for r in records],
            on_conflict="id",
        )
        return result.count

    @abstractmethod
    async def upsert(self, record: T) -> T:
        """Upsert (테이블별 충돌 키 다름).

        Args:
            record: 레코드

        Returns:
            upsert된 레코드
        """
        ...

    def _to_dict(self, record: T) -> dict[str, Any]:
        """레코드를 딕셔너리로 변환.

        Args:
            record: 레코드

        Returns:
            딕셔너리
        """
        if hasattr(record, "to_dict"):
            return record.to_dict()
        raise NotImplementedError(f"{type(record)}에 to_dict() 메서드 없음")
