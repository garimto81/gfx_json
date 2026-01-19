"""Supabase Realtime Publisher.

WebSocket 기반 실시간 이벤트 브로드캐스트.
새로운 핸드 INSERT 및 세션 상태 변경을 브로드캐스트.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


class BroadcastEvent(str, Enum):
    """브로드캐스트 이벤트 타입."""

    HAND_INSERTED = "hand_inserted"
    SESSION_UPDATED = "session_updated"
    HAND_COMPLETED = "hand_completed"


@dataclass
class BroadcastMessage:
    """브로드캐스트 메시지.

    Attributes:
        event: 이벤트 타입
        table: 테이블명
        payload: 데이터 페이로드
        timestamp: 이벤트 발생 시간
    """

    event: BroadcastEvent
    table: str
    payload: dict[str, Any]
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        """타임스탬프 기본값 설정."""
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환."""
        return {
            "event": self.event.value,
            "table": self.table,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class RealtimePublisher:
    """Supabase Realtime 퍼블리셔.

    Supabase Realtime API를 통한 WebSocket 브로드캐스트.

    특징:
    - HTTP Broadcast API 사용 (WebSocket 대신)
    - 자동 재연결 로직
    - 배치 브로드캐스트 지원
    - 에러 처리 및 로깅

    Examples:
        ```python
        publisher = RealtimePublisher(
            supabase_url="https://xxx.supabase.co",
            supabase_key="eyJhbGc...",
        )
        await publisher.connect()

        # 핸드 삽입 이벤트
        await publisher.publish_hand_inserted(
            hand_id=UUID("..."),
            session_id=123,
            hand_num=5,
        )

        # 세션 업데이트
        await publisher.publish_session_updated(
            session_id=123,
            hand_count=10,
        )

        await publisher.disconnect()
        ```
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        channel: str = "gfx_events",
        timeout: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        """초기화.

        Args:
            supabase_url: Supabase 프로젝트 URL
            supabase_key: Supabase Secret Key (또는 Anon Key)
            channel: 브로드캐스트 채널명
            timeout: 요청 타임아웃 (초)
            max_retries: 최대 재시도 횟수
        """
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self.channel = channel
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._connected = False

    async def connect(self) -> None:
        """HTTP 클라이언트 초기화."""
        if self._connected:
            logger.warning("RealtimePublisher가 이미 연결됨")
            return

        self._client = httpx.AsyncClient(
            base_url=f"{self.supabase_url}/rest/v1",
            headers={
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self.timeout),
        )
        self._connected = True
        logger.info(f"RealtimePublisher 연결: {self.supabase_url}, 채널={self.channel}")

    async def disconnect(self) -> None:
        """연결 종료."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._connected = False
            logger.info("RealtimePublisher 연결 종료")

    async def publish(
        self,
        message: BroadcastMessage,
        retry_count: int = 0,
    ) -> bool:
        """메시지 브로드캐스트.

        Args:
            message: BroadcastMessage
            retry_count: 현재 재시도 횟수 (내부 사용)

        Returns:
            성공 여부
        """
        if not self._connected or not self._client:
            logger.error("RealtimePublisher가 연결되지 않음")
            return False

        try:
            # Supabase Realtime은 PostgreSQL NOTIFY 기반
            # 또는 REST API Broadcast Endpoint 사용
            # 여기서는 간단히 rpc() 함수 호출로 구현
            response = await self._client.post(
                "/rpc/broadcast_event",
                json={
                    "channel_name": self.channel,
                    "event_data": message.to_dict(),
                },
            )

            if response.status_code in (200, 201, 204):
                logger.debug(
                    f"브로드캐스트 성공: {message.event.value}, "
                    f"table={message.table}, payload_keys={list(message.payload.keys())}"
                )
                return True

            # 실패 시 재시도
            if retry_count < self.max_retries:
                wait_time = 2**retry_count  # 지수 백오프
                logger.warning(
                    f"브로드캐스트 실패 (status={response.status_code}), "
                    f"{wait_time}초 후 재시도 ({retry_count + 1}/{self.max_retries})"
                )
                await asyncio.sleep(wait_time)
                return await self.publish(message, retry_count + 1)
            else:
                logger.error(
                    f"브로드캐스트 최종 실패: {message.event.value}, "
                    f"status={response.status_code}, body={response.text}"
                )
                return False

        except httpx.TimeoutException:
            logger.error(f"브로드캐스트 타임아웃: {message.event.value}")
            if retry_count < self.max_retries:
                await asyncio.sleep(2**retry_count)
                return await self.publish(message, retry_count + 1)
            return False

        except httpx.RequestError as e:
            logger.error(f"브로드캐스트 요청 오류: {e}")
            if retry_count < self.max_retries:
                await asyncio.sleep(2**retry_count)
                return await self.publish(message, retry_count + 1)
            return False

        except Exception as e:
            logger.exception(f"브로드캐스트 예외: {e}")
            return False

    async def publish_hand_inserted(
        self,
        hand_id: UUID,
        session_id: int,
        hand_num: int,
        player_count: int = 0,
        small_blind: float | None = None,
        big_blind: float | None = None,
    ) -> bool:
        """핸드 삽입 이벤트 브로드캐스트.

        새로운 핸드가 gfx_hands 테이블에 INSERT되었음을 알림.

        Args:
            hand_id: 핸드 UUID
            session_id: 세션 ID
            hand_num: 핸드 번호
            player_count: 플레이어 수
            small_blind: 스몰 블라인드
            big_blind: 빅 블라인드

        Returns:
            성공 여부
        """
        message = BroadcastMessage(
            event=BroadcastEvent.HAND_INSERTED,
            table="gfx_hands",
            payload={
                "hand_id": str(hand_id),
                "session_id": session_id,
                "hand_num": hand_num,
                "player_count": player_count,
                "small_blind": small_blind,
                "big_blind": big_blind,
            },
        )
        return await self.publish(message)

    async def publish_session_updated(
        self,
        session_id: int,
        hand_count: int,
        status: str | None = None,
    ) -> bool:
        """세션 업데이트 이벤트 브로드캐스트.

        세션의 핸드 카운트 또는 상태가 변경되었음을 알림.

        Args:
            session_id: 세션 ID
            hand_count: 현재 핸드 수
            status: 세션 상태 (active, completed 등)

        Returns:
            성공 여부
        """
        message = BroadcastMessage(
            event=BroadcastEvent.SESSION_UPDATED,
            table="gfx_sessions",
            payload={
                "session_id": session_id,
                "hand_count": hand_count,
                "status": status,
            },
        )
        return await self.publish(message)

    async def publish_hand_completed(
        self,
        hand_id: UUID,
        session_id: int,
        hand_num: int,
        winner_name: str | None = None,
        pot_size: float | None = None,
    ) -> bool:
        """핸드 완료 이벤트 브로드캐스트.

        핸드가 완료되고 승자가 결정되었음을 알림.

        Args:
            hand_id: 핸드 UUID
            session_id: 세션 ID
            hand_num: 핸드 번호
            winner_name: 승자 이름
            pot_size: 최종 팟 크기

        Returns:
            성공 여부
        """
        message = BroadcastMessage(
            event=BroadcastEvent.HAND_COMPLETED,
            table="gfx_hands",
            payload={
                "hand_id": str(hand_id),
                "session_id": session_id,
                "hand_num": hand_num,
                "winner_name": winner_name,
                "pot_size": pot_size,
            },
        )
        return await self.publish(message)

    async def publish_batch(
        self,
        messages: list[BroadcastMessage],
    ) -> int:
        """배치 브로드캐스트.

        여러 메시지를 순차적으로 브로드캐스트.

        Args:
            messages: BroadcastMessage 리스트

        Returns:
            성공한 메시지 수
        """
        success_count = 0
        for message in messages:
            if await self.publish(message):
                success_count += 1
            else:
                logger.warning(f"배치 브로드캐스트 실패: {message.event.value}")

        logger.info(f"배치 브로드캐스트 완료: {success_count}/{len(messages)}")
        return success_count

    @property
    def is_connected(self) -> bool:
        """연결 여부."""
        return self._connected and self._client is not None

    async def __aenter__(self) -> RealtimePublisher:
        """async with 지원."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """async with 종료."""
        await self.disconnect()


# 헬퍼 함수
async def create_publisher(
    supabase_url: str,
    supabase_key: str,
    channel: str = "gfx_events",
) -> RealtimePublisher:
    """RealtimePublisher 생성 및 연결.

    Args:
        supabase_url: Supabase URL
        supabase_key: Supabase Key
        channel: 채널명

    Returns:
        연결된 RealtimePublisher
    """
    publisher = RealtimePublisher(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        channel=channel,
    )
    await publisher.connect()
    return publisher
