"""SyncService V4와 RealtimePublisher 통합 예제.

sync_service_v4.py에서 RealtimePublisher를 사용하는 방법.
"""

from __future__ import annotations

import asyncio
import logging

from src.sync_agent.broadcast.realtime_publisher import RealtimePublisher
from src.sync_agent.core.sync_service_v4 import SyncServiceV4
from src.sync_agent.db.supabase_client import SupabaseClient
from src.sync_agent.models.base import NormalizedData
from src.sync_agent.transformers.pipeline import TransformationPipeline

logger = logging.getLogger(__name__)


class SyncServiceWithBroadcast(SyncServiceV4):
    """브로드캐스트 기능이 추가된 SyncService.

    SyncServiceV4를 확장하여 Realtime 브로드캐스트 추가.

    Examples:
        ```python
        service = SyncServiceWithBroadcast(
            client=supabase_client,
            publisher=realtime_publisher,
        )

        result = await service.sync_file("/path/to/file.json", gfx_pc_id="PC01")
        # → 파일 동기화 + 자동 브로드캐스트
        ```
    """

    def __init__(
        self,
        client: SupabaseClient,
        publisher: RealtimePublisher,
        pipeline: TransformationPipeline | None = None,
    ) -> None:
        """초기화.

        Args:
            client: SupabaseClient
            publisher: RealtimePublisher
            pipeline: TransformationPipeline (기본 생성)
        """
        super().__init__(client, pipeline)
        self.publisher = publisher

    async def _broadcast_normalized_data(
        self,
        normalized: NormalizedData,
    ) -> None:
        """NormalizedData를 브로드캐스트.

        Args:
            normalized: NormalizedData
        """
        if not self.publisher.is_connected:
            logger.warning("RealtimePublisher가 연결되지 않아 브로드캐스트 건너뜀")
            return

        # 1. 핸드 INSERT 이벤트 브로드캐스트
        for hand in normalized.hands:
            await self.publisher.publish_hand_inserted(
                hand_id=hand.id,
                session_id=hand.session_id,
                hand_num=hand.hand_num,
                player_count=hand.player_count,
                small_blind=float(hand.small_blind) if hand.small_blind else None,
                big_blind=float(hand.big_blind) if hand.big_blind else None,
            )

        # 2. 세션 업데이트 브로드캐스트
        await self.publisher.publish_session_updated(
            session_id=normalized.session.session_id,
            hand_count=len(normalized.hands),
        )

        logger.info(
            f"브로드캐스트 완료: session={normalized.session.session_id}, "
            f"hands={len(normalized.hands)}"
        )

    async def sync_from_content(
        self,
        content: str,
        gfx_pc_id: str,
        file_name: str,
        file_hash: str | None = None,
    ):
        """JSON 문자열에서 동기화 (브로드캐스트 포함).

        오버라이드: 부모 메서드 + 브로드캐스트 추가

        Args:
            content: JSON 문자열
            gfx_pc_id: GFX PC 식별자
            file_name: 파일명
            file_hash: 파일 해시

        Returns:
            SyncResultV4
        """
        # 부모 메서드 호출 (실제 동기화)
        result = await super().sync_from_content(
            content, gfx_pc_id, file_name, file_hash
        )

        # 성공 시 브로드캐스트
        if result.success:
            try:
                # 동기화된 데이터를 다시 파싱 (또는 캐시 사용)
                import json

                json_data = json.loads(content)
                normalized = self.pipeline.transform(
                    json_data=json_data,
                    gfx_pc_id=gfx_pc_id,
                    file_hash=file_hash or "",
                    file_name=file_name,
                )
                await self._broadcast_normalized_data(normalized)
            except Exception as e:
                logger.error(f"브로드캐스트 실패 (동기화는 성공): {e}")

        return result


# 사용 예제
async def example_usage():
    """통합 사용 예제."""
    # 1. SupabaseClient 생성
    client = SupabaseClient(
        url="https://your-project.supabase.co",
        secret_key="your_secret_key",
    )
    await client.connect()

    # 2. RealtimePublisher 생성
    publisher = RealtimePublisher(
        supabase_url="https://your-project.supabase.co",
        supabase_key="your_secret_key",
        channel="gfx_events",
    )
    await publisher.connect()

    # 3. SyncServiceWithBroadcast 생성
    service = SyncServiceWithBroadcast(
        client=client,
        publisher=publisher,
    )

    # 4. 파일 동기화 (자동 브로드캐스트)
    result = await service.sync_file(
        file_path="/path/to/gfx_data.json",
        gfx_pc_id="PC01",
    )

    if result.success:
        print(f"동기화 성공: session_id={result.session_id}, stats={result.stats}")
    else:
        print(f"동기화 실패: {result.error}")

    # 5. 연결 종료
    await publisher.disconnect()
    await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_usage())
