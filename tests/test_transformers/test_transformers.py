"""Transformers 단위 테스트.

TDD: Red → Green → Refactor
"""

from __future__ import annotations

from decimal import Decimal

import pytest

# 샘플 JSON 데이터
SAMPLE_SESSION_JSON = {
    "ID": 133877316553960000,
    "CreatedDateTimeUTC": "2024-10-15T10:30:00Z",
    "EventTitle": "High Stakes Cash Game",
    "SoftwareVersion": "PokerGFX 3.2",
    "Type": "FEATURE_TABLE",
    "Payouts": [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
    "Hands": [
        {
            "HandNum": 1,
            "Duration": "PT39.2342715S",
            "StartDateTimeUTC": "2024-10-15T10:30:05Z",
            "RecordingOffsetStart": "PT5M30S",
            "GameVariant": "HOLDEM",
            "GameClass": "FLOP",
            "BetStructure": "NOLIMIT",
            "AnteAmt": 0,
            "BombPotAmt": 0,
            "FlopDrawBlinds": {
                "SmallBlindAmt": 5000,
                "BigBlindAmt": 10000,
                "ButtonPlayerNum": 1,
                "SmallBlindPlayerNum": 2,
                "BigBlindPlayerNum": 3,
            },
            "Events": [
                {"EventType": "FOLD", "PlayerNum": 4, "BetAmt": 0, "Pot": 15000},
                {"EventType": "CALL", "PlayerNum": 5, "BetAmt": 10000, "Pot": 25000},
                {"EventType": "RAISE", "PlayerNum": 6, "BetAmt": 30000, "Pot": 55000},
                {"EventType": "BOARD_CARD", "PlayerNum": 0, "BoardCards": "Jd"},
                {"EventType": "BOARD_CARD", "PlayerNum": 0, "BoardCards": "7c"},
                {"EventType": "BOARD_CARD", "PlayerNum": 0, "BoardCards": "2s"},
            ],
            "Players": [
                {
                    "PlayerNum": 1,
                    "Name": "PLAYER1",
                    "LongName": "John Smith",
                    "HoleCards": [""],
                    "StartStackAmt": 100000,
                    "EndStackAmt": 85000,
                    "CumulativeWinningsAmt": -15000,
                    "VPIPPercent": 25.5,
                    "PreflopRaisePercent": 18.2,
                    "AggressionFrequencyPercent": 45.0,
                },
                {
                    "PlayerNum": 2,
                    "Name": "PLAYER2",
                    "LongName": "Jane Doe",
                    "HoleCards": ["As", "Kh"],
                    "StartStackAmt": 150000,
                    "EndStackAmt": 200000,
                    "CumulativeWinningsAmt": 50000,
                    "VPIPPercent": 32.1,
                    "PreflopRaisePercent": 22.5,
                    "AggressionFrequencyPercent": 52.3,
                },
            ],
        }
    ],
}


class TestSessionTransformer:
    """SessionTransformer 테스트."""

    def test_transform_session(self):
        """JSON Root → SessionRecord 변환."""
        from src.sync_agent.transformers.session_transformer import SessionTransformer

        transformer = SessionTransformer()
        record = transformer.transform(
            SAMPLE_SESSION_JSON, gfx_pc_id="PC01", file_hash="abc123"
        )

        assert record.session_id == 133877316553960000
        assert record.gfx_pc_id == "PC01"
        assert record.file_hash == "abc123"
        assert record.event_title == "High Stakes Cash Game"
        assert record.software_version == "PokerGFX 3.2"
        assert record.table_type == "FEATURE_TABLE"
        assert record.payouts == [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]

    def test_transform_session_missing_fields(self):
        """선택 필드 누락 시 None 처리."""
        from src.sync_agent.transformers.session_transformer import SessionTransformer

        transformer = SessionTransformer()
        minimal_json = {"ID": 12345}
        record = transformer.transform(minimal_json, gfx_pc_id="PC01", file_hash="h")

        assert record.session_id == 12345
        assert record.event_title is None
        assert record.payouts is None


class TestHandTransformer:
    """HandTransformer 테스트."""

    def test_transform_hand(self):
        """Hands[] 항목 → HandRecord 변환."""
        from src.sync_agent.transformers.hand_transformer import HandTransformer

        transformer = HandTransformer()
        hand_data = SAMPLE_SESSION_JSON["Hands"][0]
        record = transformer.transform(hand_data, session_id=12345)

        assert record.session_id == 12345
        assert record.hand_num == 1
        assert record.game_variant == "HOLDEM"
        assert record.game_class == "FLOP"
        assert record.bet_structure == "NOLIMIT"

    def test_transform_hand_blinds(self):
        """FlopDrawBlinds → blinds 필드 변환."""
        from src.sync_agent.transformers.hand_transformer import HandTransformer

        transformer = HandTransformer()
        hand_data = SAMPLE_SESSION_JSON["Hands"][0]
        record = transformer.transform(hand_data, session_id=1)

        assert record.small_blind == Decimal("5000")
        assert record.big_blind == Decimal("10000")

    def test_parse_iso_duration(self):
        """ISO 8601 Duration 파싱."""
        from src.sync_agent.transformers.hand_transformer import HandTransformer

        transformer = HandTransformer()

        assert transformer.parse_iso_duration("PT39.2342715S") == pytest.approx(
            39.23, rel=0.01
        )
        assert transformer.parse_iso_duration("PT5M30S") == pytest.approx(330, rel=0.01)
        assert transformer.parse_iso_duration("PT1H30M45S") == pytest.approx(
            5445, rel=0.01
        )
        assert transformer.parse_iso_duration(None) == 0.0


class TestPlayerTransformer:
    """PlayerTransformer 테스트."""

    def test_transform_player(self):
        """Players[] 항목 → PlayerRecord 변환."""
        from src.sync_agent.transformers.player_transformer import PlayerTransformer

        transformer = PlayerTransformer()
        player_data = SAMPLE_SESSION_JSON["Hands"][0]["Players"][0]
        record = transformer.transform(player_data)

        assert record.name == "PLAYER1"
        assert record.long_name == "John Smith"
        assert len(record.player_hash) == 32

    def test_transform_hand_player(self):
        """Players[] 항목 → HandPlayerRecord 변환."""
        from uuid import uuid4

        from src.sync_agent.transformers.player_transformer import PlayerTransformer

        transformer = PlayerTransformer()
        player_data = SAMPLE_SESSION_JSON["Hands"][0]["Players"][1]
        hand_id = uuid4()
        player_id = uuid4()

        record = transformer.transform_for_hand(player_data, hand_id, player_id)

        assert record.hand_id == hand_id
        assert record.player_id == player_id
        assert record.seat_num == 2
        assert record.hole_cards == ["As", "Kh"]
        assert record.start_stack_amt == Decimal("150000")
        assert record.end_stack_amt == Decimal("200000")
        assert record.vpip_percent == pytest.approx(32.1, rel=0.01)

    def test_parse_hole_cards(self):
        """HoleCards 파싱 (빈 문자열 필터링)."""
        from src.sync_agent.transformers.player_transformer import PlayerTransformer

        transformer = PlayerTransformer()

        assert transformer.parse_hole_cards(["As", "Kh"]) == ["As", "Kh"]
        assert transformer.parse_hole_cards([""]) == []
        assert transformer.parse_hole_cards(["As Kh"]) == ["As", "Kh"]  # 공백 분리


class TestEventTransformer:
    """EventTransformer 테스트."""

    def test_transform_action_event(self):
        """액션 이벤트 변환 (FOLD, CALL, RAISE 등)."""
        from uuid import uuid4

        from src.sync_agent.transformers.event_transformer import EventTransformer

        transformer = EventTransformer()
        hand_id = uuid4()
        event_data = SAMPLE_SESSION_JSON["Hands"][0]["Events"][1]  # CALL

        record = transformer.transform(event_data, hand_id, event_order=1)

        assert record.hand_id == hand_id
        assert record.event_order == 1
        assert record.event_type == "CALL"
        assert record.player_num == 5
        assert record.amount == Decimal("10000")
        assert record.pot == Decimal("25000")

    def test_transform_board_card_event(self):
        """BOARD_CARD 이벤트 변환."""
        from uuid import uuid4

        from src.sync_agent.transformers.event_transformer import EventTransformer

        transformer = EventTransformer()
        hand_id = uuid4()
        event_data = SAMPLE_SESSION_JSON["Hands"][0]["Events"][3]  # BOARD_CARD

        record = transformer.transform(event_data, hand_id, event_order=3)

        assert record.event_type == "BOARD_CARD"
        assert record.cards == ["Jd"]
        assert record.player_num == 0  # 보드 카드는 player_num=0


class TestTransformationPipeline:
    """TransformationPipeline 테스트."""

    def test_transform_full_json(self):
        """전체 JSON → NormalizedData 변환."""
        from src.sync_agent.transformers.pipeline import TransformationPipeline

        pipeline = TransformationPipeline()
        data = pipeline.transform(
            SAMPLE_SESSION_JSON, gfx_pc_id="PC01", file_hash="abc"
        )

        # Session
        assert data.session.session_id == 133877316553960000
        assert data.session.gfx_pc_id == "PC01"

        # Hands
        assert len(data.hands) == 1
        assert data.hands[0].hand_num == 1

        # Players (중복 제거됨)
        assert len(data.players) == 2
        player_names = {p.name for p in data.players}
        assert "PLAYER1" in player_names
        assert "PLAYER2" in player_names

        # HandPlayers
        assert len(data.hand_players) == 2

        # Events
        assert len(data.events) == 6

    def test_player_deduplication(self):
        """동일 플레이어 중복 제거."""
        from src.sync_agent.transformers.pipeline import TransformationPipeline

        # 동일 플레이어가 여러 핸드에 등장하는 JSON
        json_with_dup = {
            "ID": 1,
            "Hands": [
                {
                    "HandNum": 1,
                    "Players": [
                        {"PlayerNum": 1, "Name": "PLAYER1", "LongName": "John"}
                    ],
                    "Events": [],
                },
                {
                    "HandNum": 2,
                    "Players": [
                        {"PlayerNum": 1, "Name": "PLAYER1", "LongName": "John"}
                    ],
                    "Events": [],
                },
            ],
        }

        pipeline = TransformationPipeline()
        data = pipeline.transform(json_with_dup, gfx_pc_id="PC01", file_hash="h")

        # 플레이어는 1명만 (중복 제거)
        assert len(data.players) == 1
        # HandPlayers는 2개 (각 핸드별)
        assert len(data.hand_players) == 2

    def test_stats_property(self):
        """NormalizedData.stats 속성."""
        from src.sync_agent.transformers.pipeline import TransformationPipeline

        pipeline = TransformationPipeline()
        data = pipeline.transform(SAMPLE_SESSION_JSON, gfx_pc_id="PC01", file_hash="h")

        stats = data.stats
        assert stats["hands"] == 1
        assert stats["players"] == 2
        assert stats["hand_players"] == 2
        assert stats["events"] == 6
