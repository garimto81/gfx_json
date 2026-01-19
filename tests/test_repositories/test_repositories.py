"""Repositories 단위 테스트.

TDD: Red → Green → Refactor
Mock을 사용하여 SupabaseClient 의존성 분리.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.sync_agent.db.supabase_client import UpsertResult


@pytest.fixture
def mock_client():
    """Mock SupabaseClient."""
    client = AsyncMock()
    client.upsert = AsyncMock(return_value=UpsertResult(success=True, count=1))
    client.select = AsyncMock(return_value=[])
    return client


class TestBaseRepository:
    """BaseRepository 테스트."""

    @pytest.mark.asyncio
    async def test_create_single(self, mock_client):
        """단건 생성."""
        from src.sync_agent.models.session import SessionRecord
        from src.sync_agent.repositories.session_repo import SessionRepository

        repo = SessionRepository(mock_client)
        record = SessionRecord(
            session_id=12345,
            gfx_pc_id="PC01",
            file_hash="hash",
            file_name="test.json",
        )

        result = await repo.create(record)

        assert result == record
        mock_client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_many(self, mock_client):
        """다건 생성."""
        from src.sync_agent.models.session import SessionRecord
        from src.sync_agent.repositories.session_repo import SessionRepository

        mock_client.upsert = AsyncMock(return_value=UpsertResult(success=True, count=3))
        repo = SessionRepository(mock_client)

        records = [
            SessionRecord(
                session_id=i, gfx_pc_id="PC01", file_hash=f"h{i}", file_name=f"{i}.json"
            )
            for i in range(3)
        ]

        count = await repo.create_many(records)

        assert count == 3


class TestPlayerRepository:
    """PlayerRepository 테스트."""

    @pytest.mark.asyncio
    async def test_upsert_by_hash(self, mock_client):
        """player_hash 기준 upsert."""
        from src.sync_agent.models.player import PlayerRecord
        from src.sync_agent.repositories.player_repo import PlayerRepository

        repo = PlayerRepository(mock_client)
        player = PlayerRecord.create(name="Test", long_name="Test Player")

        await repo.upsert(player)

        mock_client.upsert.assert_called_once()
        call_kwargs = mock_client.upsert.call_args.kwargs
        assert call_kwargs["on_conflict"] == "player_hash"

    @pytest.mark.asyncio
    async def test_find_by_hash(self, mock_client):
        """해시로 조회."""
        from src.sync_agent.repositories.player_repo import PlayerRepository

        mock_client.select = AsyncMock(
            return_value=[
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "player_hash": "abc123",
                    "name": "Test",
                    "long_name": "Test Player",
                    "first_seen_at": "2024-01-01T00:00:00+00:00",
                    "last_seen_at": "2024-01-01T00:00:00+00:00",
                    "total_hands": 0,
                    "created_at": "2024-01-01T00:00:00+00:00",
                }
            ]
        )

        repo = PlayerRepository(mock_client)
        result = await repo.find_by_hash("abc123")

        assert result is not None
        assert result.name == "Test"


class TestSessionRepository:
    """SessionRepository 테스트."""

    @pytest.mark.asyncio
    async def test_upsert_by_session_id(self, mock_client):
        """session_id 기준 upsert."""
        from src.sync_agent.models.session import SessionRecord
        from src.sync_agent.repositories.session_repo import SessionRepository

        repo = SessionRepository(mock_client)
        session = SessionRecord(
            session_id=12345,
            gfx_pc_id="PC01",
            file_hash="hash",
            file_name="test.json",
        )

        await repo.upsert(session)

        call_kwargs = mock_client.upsert.call_args.kwargs
        assert call_kwargs["on_conflict"] == "session_id"


class TestHandRepository:
    """HandRepository 테스트."""

    @pytest.mark.asyncio
    async def test_create_hand(self, mock_client):
        """핸드 생성."""
        from src.sync_agent.models.hand import HandRecord
        from src.sync_agent.repositories.hand_repo import HandRepository

        repo = HandRepository(mock_client)
        hand = HandRecord(session_id=12345, hand_num=1)

        result = await repo.create(hand)

        assert result.hand_num == 1


class TestEventRepository:
    """EventRepository 테스트."""

    @pytest.mark.asyncio
    async def test_create_events_batch(self, mock_client):
        """이벤트 배치 생성."""
        from uuid import uuid4

        from src.sync_agent.models.event import EventRecord
        from src.sync_agent.repositories.event_repo import EventRepository

        mock_client.upsert = AsyncMock(return_value=UpsertResult(success=True, count=3))
        repo = EventRepository(mock_client)
        hand_id = uuid4()

        events = [
            EventRecord(hand_id=hand_id, event_order=i, event_type="FOLD")
            for i in range(3)
        ]

        count = await repo.create_many(events)

        assert count == 3


class TestUnitOfWork:
    """UnitOfWork 테스트."""

    @pytest.mark.asyncio
    async def test_save_normalized_success(self, mock_client):
        """정규화 데이터 저장 성공."""
        from src.sync_agent.models.base import NormalizedData
        from src.sync_agent.models.event import EventRecord
        from src.sync_agent.models.hand import HandRecord
        from src.sync_agent.models.player import HandPlayerRecord, PlayerRecord
        from src.sync_agent.models.session import SessionRecord
        from src.sync_agent.repositories.unit_of_work import UnitOfWork

        # 테스트 데이터 준비
        session = SessionRecord(
            session_id=1, gfx_pc_id="PC01", file_hash="h", file_name="f.json"
        )
        hands = [HandRecord(session_id=1, hand_num=1)]
        players = [PlayerRecord.create(name="P1", long_name="Player 1")]
        hand_players = [
            HandPlayerRecord(hand_id=hands[0].id, player_id=players[0].id, player_num=1)
        ]
        events = [EventRecord(hand_id=hands[0].id, event_order=0, event_type="FOLD")]

        data = NormalizedData(
            session=session,
            hands=hands,
            players=players,
            hand_players=hand_players,
            events=events,
        )

        uow = UnitOfWork(mock_client)
        result = await uow.save_normalized(data)

        assert result.success is True
        assert "players" in result.stats
        assert result.stats["players"] == 1

    @pytest.mark.asyncio
    async def test_save_normalized_order(self, mock_client):
        """저장 순서 검증: Players → Sessions → Hands → HandPlayers → Events."""
        from src.sync_agent.models.base import NormalizedData
        from src.sync_agent.models.event import EventRecord
        from src.sync_agent.models.hand import HandRecord
        from src.sync_agent.models.player import HandPlayerRecord, PlayerRecord
        from src.sync_agent.models.session import SessionRecord
        from src.sync_agent.repositories.unit_of_work import UnitOfWork

        call_order = []

        async def track_upsert(table, **kwargs):
            call_order.append(table)
            return UpsertResult(success=True, count=1)

        mock_client.upsert = track_upsert

        session = SessionRecord(
            session_id=1, gfx_pc_id="PC01", file_hash="h", file_name="f.json"
        )
        hands = [HandRecord(session_id=1, hand_num=1)]
        players = [PlayerRecord.create(name="P1")]
        hand_players = [
            HandPlayerRecord(hand_id=hands[0].id, player_id=players[0].id, player_num=1)
        ]
        events = [EventRecord(hand_id=hands[0].id, event_order=0, event_type="FOLD")]

        data = NormalizedData(
            session=session,
            hands=hands,
            players=players,
            hand_players=hand_players,
            events=events,
        )

        uow = UnitOfWork(mock_client)
        await uow.save_normalized(data)

        # 순서 검증: gfx_players → gfx_sessions → gfx_hands → gfx_hand_players → gfx_events
        assert call_order[0] == "gfx_players"
        assert call_order[1] == "gfx_sessions"
        assert call_order[2] == "gfx_hands"
        assert call_order[3] == "gfx_hand_players"
        assert call_order[4] == "gfx_events"

    @pytest.mark.asyncio
    async def test_save_normalized_partial_failure(self, mock_client):
        """부분 실패 시 에러 반환."""
        from src.sync_agent.models.base import NormalizedData
        from src.sync_agent.models.hand import HandRecord
        from src.sync_agent.models.player import PlayerRecord
        from src.sync_agent.models.session import SessionRecord
        from src.sync_agent.repositories.unit_of_work import UnitOfWork

        # Hands 저장 시 실패
        call_count = 0

        async def fail_on_hands(table, **kwargs):
            nonlocal call_count
            call_count += 1
            if table == "gfx_hands":
                raise Exception("DB Error")
            return UpsertResult(success=True, count=1)

        mock_client.upsert = fail_on_hands

        data = NormalizedData(
            session=SessionRecord(
                session_id=1, gfx_pc_id="PC01", file_hash="h", file_name="f.json"
            ),
            hands=[HandRecord(session_id=1, hand_num=1)],
            players=[PlayerRecord.create(name="P1")],
            hand_players=[],
            events=[],
        )

        uow = UnitOfWork(mock_client)
        result = await uow.save_normalized(data)

        assert result.success is False
        assert "DB Error" in result.error
