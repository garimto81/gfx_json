"""Models 단위 테스트.

TDD: Red → Green → Refactor
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID


class TestBaseRecord:
    """BaseRecord 테스트."""

    def test_base_record_has_id(self):
        """BaseRecord는 UUID id를 가진다."""
        from src.sync_agent.models.base import BaseRecord

        record = BaseRecord()
        assert isinstance(record.id, UUID)

    def test_base_record_has_created_at(self):
        """BaseRecord는 created_at 타임스탬프를 가진다."""
        from src.sync_agent.models.base import BaseRecord

        record = BaseRecord()
        assert isinstance(record.created_at, datetime)

    def test_base_record_to_dict(self):
        """BaseRecord.to_dict()는 딕셔너리를 반환한다."""
        from src.sync_agent.models.base import BaseRecord

        record = BaseRecord()
        d = record.to_dict()
        assert isinstance(d, dict)
        assert "id" in d
        assert "created_at" in d


class TestPlayerRecord:
    """PlayerRecord 테스트."""

    def test_player_record_fields(self):
        """PlayerRecord는 필수 필드를 가진다."""
        from src.sync_agent.models.player import PlayerRecord

        player = PlayerRecord(
            name="TestPlayer",
            long_name="Test Player Full Name",
        )
        assert player.name == "TestPlayer"
        assert player.long_name == "Test Player Full Name"
        assert isinstance(player.id, UUID)

    def test_generate_player_hash(self):
        """player_hash는 MD5(name:long_name)으로 생성된다."""
        from src.sync_agent.models.player import PlayerRecord

        hash1 = PlayerRecord.generate_hash("Player1", "Full Name")
        hash2 = PlayerRecord.generate_hash("Player1", "Full Name")
        hash3 = PlayerRecord.generate_hash("Player2", "Full Name")

        assert hash1 == hash2  # 동일 입력 = 동일 해시
        assert hash1 != hash3  # 다른 입력 = 다른 해시
        assert len(hash1) == 32  # MD5 해시 길이

    def test_generate_hash_with_none_long_name(self):
        """long_name이 None이어도 해시 생성 가능."""
        from src.sync_agent.models.player import PlayerRecord

        hash1 = PlayerRecord.generate_hash("Player1", None)
        hash2 = PlayerRecord.generate_hash("Player1", "")

        assert hash1 == hash2  # None과 빈 문자열은 동일 취급

    def test_player_record_to_dict(self):
        """PlayerRecord.to_dict()는 Supabase용 딕셔너리를 반환한다."""
        from src.sync_agent.models.player import PlayerRecord

        player = PlayerRecord(
            name="Test",
            long_name="Test Full",
            player_hash="abc123",
        )
        d = player.to_dict()

        assert d["name"] == "Test"
        assert d["long_name"] == "Test Full"
        assert d["player_hash"] == "abc123"
        assert "id" in d

    def test_player_record_create_with_auto_hash(self):
        """PlayerRecord.create()는 자동으로 해시를 생성한다."""
        from src.sync_agent.models.player import PlayerRecord

        player = PlayerRecord.create(name="Test", long_name="Test Full")

        assert player.player_hash != ""
        assert len(player.player_hash) == 32


class TestHandPlayerRecord:
    """HandPlayerRecord 테스트."""

    def test_hand_player_record_fields(self):
        """HandPlayerRecord는 핸드별 플레이어 정보를 저장한다."""
        from uuid import uuid4

        from src.sync_agent.models.player import HandPlayerRecord

        hand_id = uuid4()
        player_id = uuid4()

        hp = HandPlayerRecord(
            hand_id=hand_id,
            player_id=player_id,
            seat_num=3,
            hole_cards=["As", "Kh"],
            start_stack_amt=Decimal("10000"),
            end_stack_amt=Decimal("15000"),
        )

        assert hp.hand_id == hand_id
        assert hp.player_id == player_id
        assert hp.seat_num == 3
        assert hp.hole_cards == ["As", "Kh"]
        assert hp.start_stack_amt == Decimal("10000")

    def test_hand_player_record_to_dict(self):
        """HandPlayerRecord.to_dict()는 딕셔너리를 반환한다."""
        from uuid import uuid4

        from src.sync_agent.models.player import HandPlayerRecord

        hp = HandPlayerRecord(
            hand_id=uuid4(),
            player_id=uuid4(),
            seat_num=1,
        )
        d = hp.to_dict()

        assert "hand_id" in d
        assert "player_id" in d
        assert "seat_num" in d


class TestSessionRecord:
    """SessionRecord 테스트."""

    def test_session_record_fields(self):
        """SessionRecord는 세션 메타데이터를 저장한다."""
        from src.sync_agent.models.session import SessionRecord

        session = SessionRecord(
            session_id=133877316553960000,
            gfx_pc_id="PC01",
            file_hash="abc123def456",
            file_name="PGFX_live_data_export.json",
            event_title="High Stakes Game",
            table_type="FEATURE_TABLE",
        )

        assert session.session_id == 133877316553960000
        assert session.gfx_pc_id == "PC01"
        assert session.file_hash == "abc123def456"

    def test_session_record_payouts(self):
        """SessionRecord는 payouts 배열을 저장한다."""
        from src.sync_agent.models.session import SessionRecord

        session = SessionRecord(
            session_id=1,
            gfx_pc_id="PC01",
            file_hash="hash",
            file_name="test.json",
            payouts=[100, 200, 300],
        )

        assert session.payouts == [100, 200, 300]

    def test_session_record_to_dict(self):
        """SessionRecord.to_dict()는 딕셔너리를 반환한다."""
        from src.sync_agent.models.session import SessionRecord

        session = SessionRecord(
            session_id=12345,
            gfx_pc_id="PC01",
            file_hash="hash123",
            file_name="test.json",
        )
        d = session.to_dict()

        assert d["session_id"] == 12345
        assert d["gfx_pc_id"] == "PC01"
        assert "id" in d


class TestHandRecord:
    """HandRecord 테스트."""

    def test_hand_record_fields(self):
        """HandRecord는 핸드 정보를 저장한다."""
        from src.sync_agent.models.hand import HandRecord

        hand = HandRecord(
            session_id=12345,
            hand_num=1,
            game_variant="HOLDEM",
            game_class="FLOP",
            bet_structure="NOLIMIT",
            duration_seconds=120.5,
        )

        assert hand.session_id == 12345
        assert hand.hand_num == 1
        assert hand.game_variant == "HOLDEM"
        assert hand.duration_seconds == 120.5

    def test_hand_record_blinds(self):
        """HandRecord는 블라인드 정보를 저장한다."""
        from src.sync_agent.models.hand import HandRecord

        hand = HandRecord(
            session_id=1,
            hand_num=1,
            small_blind=Decimal("50"),
            big_blind=Decimal("100"),
            ante=Decimal("10"),
        )

        assert hand.small_blind == Decimal("50")
        assert hand.big_blind == Decimal("100")
        assert hand.ante == Decimal("10")

    def test_hand_record_to_dict(self):
        """HandRecord.to_dict()는 딕셔너리를 반환한다."""
        from src.sync_agent.models.hand import HandRecord

        hand = HandRecord(session_id=1, hand_num=5)
        d = hand.to_dict()

        assert d["session_id"] == 1
        assert d["hand_num"] == 5
        assert "id" in d


class TestEventRecord:
    """EventRecord 테스트."""

    def test_event_record_fields(self):
        """EventRecord는 이벤트 정보를 저장한다."""
        from uuid import uuid4

        from src.sync_agent.models.event import EventRecord

        hand_id = uuid4()
        event = EventRecord(
            hand_id=hand_id,
            event_order=0,
            event_type="BET",
            player_num=3,
            amount=Decimal("500"),
        )

        assert event.hand_id == hand_id
        assert event.event_order == 0
        assert event.event_type == "BET"
        assert event.player_num == 3
        assert event.amount == Decimal("500")

    def test_event_record_board_card(self):
        """BOARD_CARD 이벤트는 cards 필드를 가진다."""
        from uuid import uuid4

        from src.sync_agent.models.event import EventRecord

        event = EventRecord(
            hand_id=uuid4(),
            event_order=10,
            event_type="BOARD_CARD",
            cards=["Jd", "7c", "2s"],
        )

        assert event.event_type == "BOARD_CARD"
        assert event.cards == ["Jd", "7c", "2s"]

    def test_event_record_to_dict(self):
        """EventRecord.to_dict()는 딕셔너리를 반환한다."""
        from uuid import uuid4

        from src.sync_agent.models.event import EventRecord

        event = EventRecord(
            hand_id=uuid4(),
            event_order=5,
            event_type="FOLD",
        )
        d = event.to_dict()

        assert "hand_id" in d
        assert d["event_order"] == 5
        assert d["event_type"] == "FOLD"


class TestNormalizedData:
    """NormalizedData 테스트."""

    def test_normalized_data_container(self):
        """NormalizedData는 정규화된 데이터 컨테이너이다."""
        from src.sync_agent.models.base import NormalizedData
        from src.sync_agent.models.event import EventRecord
        from src.sync_agent.models.hand import HandRecord
        from src.sync_agent.models.player import HandPlayerRecord, PlayerRecord
        from src.sync_agent.models.session import SessionRecord

        session = SessionRecord(
            session_id=1, gfx_pc_id="PC01", file_hash="h", file_name="f.json"
        )
        hands = [HandRecord(session_id=1, hand_num=1)]
        players = [PlayerRecord.create(name="P1", long_name="Player 1")]
        hand_players = [
            HandPlayerRecord(
                hand_id=hands[0].id,
                player_id=players[0].id,
                seat_num=1,
            )
        ]
        events = [EventRecord(hand_id=hands[0].id, event_order=0, event_type="FOLD")]

        data = NormalizedData(
            session=session,
            hands=hands,
            players=players,
            hand_players=hand_players,
            events=events,
        )

        assert data.session.session_id == 1
        assert len(data.hands) == 1
        assert len(data.players) == 1
        assert len(data.hand_players) == 1
        assert len(data.events) == 1
