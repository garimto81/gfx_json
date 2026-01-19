"""Base Transformer 정의.

변환기 프로토콜.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class BaseTransformer(Protocol[T]):
    """변환기 프로토콜.

    모든 Transformer가 구현해야 하는 인터페이스.
    """

    def transform(self, data: dict[str, Any], **kwargs: Any) -> T:
        """데이터 변환.

        Args:
            data: 원본 JSON 데이터
            **kwargs: 추가 파라미터

        Returns:
            변환된 레코드
        """
        ...

    def validate(self, data: dict[str, Any]) -> list[str]:
        """데이터 검증.

        Args:
            data: 원본 JSON 데이터

        Returns:
            에러 메시지 리스트 (빈 리스트면 유효)
        """
        ...
