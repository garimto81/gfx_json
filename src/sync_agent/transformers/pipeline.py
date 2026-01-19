"""Transformation Pipeline.

전체 JSON → NormalizedData 변환 오케스트레이션.
"""

from __future__ import annotations

from typing import Any

from src.sync_agent.models.base import NormalizedData
from src.sync_agent.models.event import EventRecord
from src.sync_agent.models.hand import HandRecord
from src.sync_agent.models.player import HandPlayerRecord, PlayerRecord
from src.sync_agent.models.session import SessionRecord
from src.sync_agent.transformers.event_transformer import EventTransformer
from src.sync_agent.transformers.hand_transformer import HandTransformer
from src.sync_agent.transformers.player_transformer import PlayerTransformer
from src.sync_agent.transformers.session_transformer import SessionTransformer


class TransformationPipeline:
    """전체 변환 파이프라인.

    JSON Root → NormalizedData (7개 테이블용 데이터).

    플레이어 중복 제거:
    - player_hash 기반으로 동일 플레이어 식별
    - 여러 핸드에 등장해도 gfx_players에는 1건만

    Examples:
        ```python
        pipeline = TransformationPipeline()
        data = pipeline.transform(json_data, gfx_pc_id="PC01", file_hash="abc")

        # data.session: SessionRecord
        # data.hands: list[HandRecord]
        # data.players: list[PlayerRecord] (중복 제거)
        # data.hand_players: list[HandPlayerRecord]
        # data.events: list[EventRecord]
        ```
    """

    def __init__(
        self,
        session_transformer: SessionTransformer | None = None,
        hand_transformer: HandTransformer | None = None,
        player_transformer: PlayerTransformer | None = None,
        event_transformer: EventTransformer | None = None,
    ) -> None:
        """초기화.

        Args:
            session_transformer: Session 변환기 (기본 생성)
            hand_transformer: Hand 변환기 (기본 생성)
            player_transformer: Player 변환기 (기본 생성)
            event_transformer: Event 변환기 (기본 생성)
        """
        self.session_t = session_transformer or SessionTransformer()
        self.hand_t = hand_transformer or HandTransformer()
        self.player_t = player_transformer or PlayerTransformer()
        self.event_t = event_transformer or EventTransformer()

    def transform(
        self,
        json_data: dict[str, Any],
        gfx_pc_id: str,
        file_hash: str,
        file_name: str = "",
    ) -> NormalizedData:
        """JSON → NormalizedData 변환.

        변환 순서:
        1. Session (Root)
        2. Hands (Hands[])
        3. Players (Hands[].Players[]) - 중복 제거
        4. HandPlayers (Hands[].Players[])
        5. Events (Hands[].Events[])

        Args:
            json_data: JSON Root 객체
            gfx_pc_id: GFX PC 식별자
            file_hash: 파일 해시
            file_name: 파일명

        Returns:
            NormalizedData
        """
        # 플레이어 캐시 (player_hash → PlayerRecord)
        player_cache: dict[str, PlayerRecord] = {}

        # 1. Session
        session = self.session_t.transform(
            json_data, gfx_pc_id=gfx_pc_id, file_hash=file_hash, file_name=file_name
        )

        hands: list[HandRecord] = []
        hand_players: list[HandPlayerRecord] = []
        events: list[EventRecord] = []

        # 2. Hands 순회
        for hand_data in json_data.get("Hands", []):
            hand = self.hand_t.transform(hand_data, session_id=session.session_id)
            hands.append(hand)

            # 3. Players 순회 (핸드별)
            for player_data in hand_data.get("Players", []):
                # 마스터 플레이어 생성/조회
                player = self.player_t.transform(player_data)

                # 중복 제거 (캐시 활용)
                if player.player_hash not in player_cache:
                    player_cache[player.player_hash] = player
                else:
                    # 기존 플레이어 사용
                    player = player_cache[player.player_hash]

                # HandPlayer 생성
                hp = self.player_t.transform_for_hand(
                    player_data, hand_id=hand.id, player_id=player.id
                )
                hand_players.append(hp)

            # 4. Events 순회
            for idx, event_data in enumerate(hand_data.get("Events", [])):
                event = self.event_t.transform(
                    event_data, hand_id=hand.id, event_order=idx
                )
                events.append(event)

        return NormalizedData(
            session=session,
            hands=hands,
            players=list(player_cache.values()),
            hand_players=hand_players,
            events=events,
        )

    def validate(self, json_data: dict[str, Any]) -> list[str]:
        """전체 JSON 검증.

        Args:
            json_data: JSON Root 객체

        Returns:
            에러 메시지 리스트
        """
        errors = []

        # Session 검증
        errors.extend(self.session_t.validate(json_data))

        # Hands 검증
        for i, hand_data in enumerate(json_data.get("Hands", [])):
            hand_errors = self.hand_t.validate(hand_data)
            for err in hand_errors:
                errors.append(f"Hands[{i}]: {err}")

        return errors
