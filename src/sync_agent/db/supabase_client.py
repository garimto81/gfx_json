"""Supabase REST API 클라이언트 모듈.

httpx 기반 비동기 HTTP 클라이언트.
Rate Limit 예외 처리 포함.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Rate Limit 초과 예외 (HTTP 429)."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class SupabaseAPIError(Exception):
    """Supabase API 오류."""

    def __init__(self, status_code: int, message: str, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


@dataclass
class UpsertResult:
    """Upsert 결과."""

    success: bool
    count: int = 0
    error: str | None = None


class SupabaseClient:
    """httpx 기반 Supabase REST 클라이언트.

    기능:
    - 비동기 HTTP 요청 (httpx.AsyncClient)
    - Upsert 지원 (on_conflict)
    - Rate Limit 예외 분리 (HTTP 429)
    - 연결 상태 관리

    Examples:
        ```python
        client = SupabaseClient(
            url="https://xxx.supabase.co",
            secret_key="sb_secret_xxx",
        )
        await client.connect()

        # Upsert
        result = await client.upsert(
            table="gfx_sessions",
            records=[{"file_hash": "abc", "data": {...}}],
            on_conflict="gfx_pc_id,file_hash",
        )

        await client.close()
        ```
    """

    def __init__(
        self,
        url: str,
        secret_key: str,
        timeout: float = 30.0,
    ) -> None:
        """초기화.

        Args:
            url: Supabase 프로젝트 URL
            secret_key: Supabase Secret Key (sb_secret_xxx)
            timeout: 요청 타임아웃 (초)
        """
        self.url = url.rstrip("/")
        self.secret_key = secret_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """HTTP 클라이언트 초기화."""
        self._client = httpx.AsyncClient(
            base_url=f"{self.url}/rest/v1",
            headers={
                "apikey": self.secret_key,
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",  # 응답 최소화
            },
            timeout=httpx.Timeout(self.timeout),
        )
        logger.info(f"SupabaseClient 연결: {self.url}")

    async def close(self) -> None:
        """클라이언트 종료."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("SupabaseClient 연결 종료")

    async def upsert(
        self,
        table: str,
        records: list[dict[str, Any]],
        on_conflict: str = "file_hash",
    ) -> UpsertResult:
        """Upsert 실행.

        Args:
            table: 테이블명
            records: 레코드 리스트
            on_conflict: 충돌 키 (쉼표로 구분)

        Returns:
            UpsertResult

        Raises:
            RateLimitError: HTTP 429 응답 시
            SupabaseAPIError: 기타 API 오류 시
            RuntimeError: 미연결 시
        """
        self._ensure_connected()

        if not records:
            return UpsertResult(success=True, count=0)

        try:
            response = await self._client.post(
                f"/{table}",
                json=records,
                headers={
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                params={"on_conflict": on_conflict},
            )

            return self._handle_response(response, len(records))

        except httpx.TimeoutException as e:
            logger.error(f"Supabase 타임아웃: {e}")
            return UpsertResult(success=False, count=0, error="timeout")

        except httpx.RequestError as e:
            logger.error(f"Supabase 요청 오류: {e}")
            return UpsertResult(success=False, count=0, error=str(e))

    async def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select 쿼리.

        Args:
            table: 테이블명
            columns: 조회할 컬럼 (기본: *)
            filters: 필터 조건 (eq 연산)
            limit: 최대 조회 개수

        Returns:
            레코드 리스트
        """
        self._ensure_connected()

        params = {"select": columns}
        if limit:
            params["limit"] = str(limit)

        # 필터 적용 (eq 연산만 지원)
        if filters:
            for key, value in filters.items():
                params[key] = f"eq.{value}"

        response = await self._client.get(f"/{table}", params=params)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(retry_after=int(retry_after) if retry_after else None)

        response.raise_for_status()
        return response.json()

    async def delete(
        self,
        table: str,
        filters: dict[str, Any],
    ) -> int:
        """레코드 삭제.

        Args:
            table: 테이블명
            filters: 필터 조건 (eq 연산)

        Returns:
            삭제된 건수 (Prefer: return=representation 필요)
        """
        self._ensure_connected()

        params = {}
        for key, value in filters.items():
            params[key] = f"eq.{value}"

        response = await self._client.delete(
            f"/{table}",
            params=params,
            headers={"Prefer": "return=representation"},
        )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(retry_after=int(retry_after) if retry_after else None)

        response.raise_for_status()

        # 삭제된 레코드 수 반환
        deleted = response.json()
        return len(deleted) if isinstance(deleted, list) else 0

    async def health_check(self) -> bool:
        """연결 상태 확인.

        Returns:
            연결 성공 여부
        """
        if not self._client:
            return False

        try:
            # 간단한 쿼리로 연결 확인
            response = await self._client.get(
                "/",
                params={"select": "1", "limit": "1"},
                timeout=5.0,
            )
            return response.status_code in (200, 400)  # 400도 연결은 됨
        except Exception as e:
            logger.warning(f"헬스체크 실패: {e}")
            return False

    def _handle_response(self, response: httpx.Response, record_count: int) -> UpsertResult:
        """응답 처리.

        Args:
            response: HTTP 응답
            record_count: 요청한 레코드 수

        Returns:
            UpsertResult

        Raises:
            RateLimitError: HTTP 429
            SupabaseAPIError: 기타 4xx/5xx
        """
        status = response.status_code

        # Rate Limit
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            logger.warning(f"Rate Limit 초과, Retry-After: {retry_after}")
            raise RateLimitError(retry_after=int(retry_after) if retry_after else None)

        # 성공
        if 200 <= status < 300:
            logger.debug(f"Upsert 성공: {record_count}건")
            return UpsertResult(success=True, count=record_count)

        # 클라이언트 오류
        if 400 <= status < 500:
            error_body = response.text
            logger.error(f"Supabase 클라이언트 오류 {status}: {error_body}")
            raise SupabaseAPIError(status, f"Client error: {status}", error_body)

        # 서버 오류
        if status >= 500:
            error_body = response.text
            logger.error(f"Supabase 서버 오류 {status}: {error_body}")
            return UpsertResult(success=False, count=0, error=f"Server error: {status}")

        # 기타
        return UpsertResult(success=False, count=0, error=f"Unknown status: {status}")

    def _ensure_connected(self) -> None:
        """연결 상태 확인."""
        if self._client is None:
            raise RuntimeError("SupabaseClient가 연결되지 않음. connect() 먼저 호출하세요.")

    @property
    def is_connected(self) -> bool:
        """연결 여부."""
        return self._client is not None

    async def __aenter__(self) -> "SupabaseClient":
        """async with 지원."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """async with 종료."""
        await self.close()
