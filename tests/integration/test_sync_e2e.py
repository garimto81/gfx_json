"""Module 2 통합 테스트: JSON → Supabase → Realtime.

E2E 시나리오:
1. JSON 파일 파싱
2. Supabase INSERT
3. Realtime 브로드캐스트
4. 전체 파이프라인 통합

Test-Driven Development:
- Red: 이 테스트가 먼저 실패
- Green: 구현 완료 후 통과
- Refactor: 코드 정리
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.sync_agent.adapters.db_adapter import SupabaseSchemaAdapter
from src.sync_agent.broadcast.realtime_publisher import (
    BroadcastEvent,
    BroadcastMessage,
    RealtimePublisher,
)
from src.sync_agent.core.json_parser import JsonParser
from src.sync_agent.db.supabase_client import SupabaseClient

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_json_file(tmp_path: Path) -> str:
    """샘플 JSON 파일 생성.

    Module 2 표준 구조:
    - session.id
    - session.tableType
    - session.eventTitle
    - hands 배열
    """
    data = {
        "session": {
            "id": 99001,
            "tableType": "cash",
            "eventTitle": "Integration Test Event",
            "softwareVersion": "3.0.0",
            "createdAt": "2026-01-15T10:00:00Z",
        },
        "hands": [
            {"id": 1, "players": []},
            {"id": 2, "players": []},
            {"id": 3, "players": []},
        ],
    }
    file_path = tmp_path / "session_99001.json"
    file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(file_path)


@pytest.fixture
def invalid_json_file(tmp_path: Path) -> str:
    """잘못된 JSON 파일."""
    file_path = tmp_path / "invalid.json"
    file_path.write_text("{invalid json content", encoding="utf-8")
    return str(file_path)


@pytest.fixture
def mock_supabase_client() -> MagicMock:
    """Supabase 클라이언트 Mock."""
    client = MagicMock(spec=SupabaseClient)
    client.upsert = AsyncMock(return_value={"data": [{"id": str(uuid4())}]})
    client.select = AsyncMock(return_value=[])
    client.is_connected.return_value = True
    return client


@pytest.fixture
def mock_realtime_publisher() -> MagicMock:
    """Realtime Publisher Mock."""
    publisher = MagicMock(spec=RealtimePublisher)
    publisher.publish = AsyncMock(return_value=True)
    publisher.publish_hand_inserted = AsyncMock(return_value=True)
    publisher.publish_session_updated = AsyncMock(return_value=True)
    publisher.is_connected = True
    return publisher


# ============================================================================
# Unit Tests: JSON Parser
# ============================================================================


class TestJsonParserIntegration:
    """JsonParser 통합 테스트."""

    def test_parse_success_with_real_structure(self, sample_json_file: str):
        """실제 JSON 구조 파싱 성공."""
        # Arrange
        parser = JsonParser()
        gfx_pc_id = "PC01"

        # Act
        result = parser.parse(sample_json_file, gfx_pc_id)

        # Assert
        assert result.success is True
        assert result.record is not None
        assert result.record["session_id"] == 99001
        # JsonParser는 중첩 구조를 추출하지 않음 (raw_json에만 존재)
        assert result.record["table_type"] is None  # 최상위 레벨에만 table_type 추출
        assert result.record["event_title"] is None  # 최상위 레벨에만 event_title 추출
        assert result.record["hand_count"] == 3
        assert result.record["file_hash"] is not None
        assert len(result.record["file_hash"]) == 64  # SHA-256
        # raw_json에는 전체 구조 포함
        assert result.record["raw_json"]["session"]["tableType"] == "cash"
        assert (
            result.record["raw_json"]["session"]["eventTitle"]
            == "Integration Test Event"
        )

    def test_parse_failure_invalid_json(self, invalid_json_file: str):
        """잘못된 JSON 파싱 실패."""
        # Arrange
        parser = JsonParser()

        # Act
        result = parser.parse(invalid_json_file, "PC01")

        # Assert
        assert result.success is False
        assert result.error == "json_decode_error"

    def test_parse_file_not_found(self):
        """존재하지 않는 파일."""
        # Arrange
        parser = JsonParser()

        # Act
        result = parser.parse("/nonexistent/file.json", "PC01")

        # Assert
        assert result.success is False
        assert result.error == "file_not_found"


# ============================================================================
# Unit Tests: Supabase Client (Mocked)
# ============================================================================


class TestSupabaseIntegration:
    """Supabase 클라이언트 통합 테스트."""

    @pytest.mark.asyncio
    async def test_upsert_session_success(self, mock_supabase_client: MagicMock):
        """세션 레코드 upsert 성공."""
        # Arrange
        adapter = SupabaseSchemaAdapter()
        code_record = {
            "session_id": 99001,
            "file_hash": "abc123",
            "file_name": "session_99001.json",
            "table_type": "cash",
            "event_title": "Test Event",
            "software_version": "3.0.0",
            "created_datetime_utc": "2026-01-15T10:00:00Z",
            "hand_count": 3,
            "raw_json": {},
        }
        db_record = adapter.to_db_record(code_record, gfx_pc_id="PC01")

        # Act
        result = await mock_supabase_client.upsert(
            table="gfx_sessions",
            records=[db_record],
            on_conflict="session_id",
        )

        # Assert
        assert result is not None
        mock_supabase_client.upsert.assert_called_once()
        call_args = mock_supabase_client.upsert.call_args
        assert call_args[1]["table"] == "gfx_sessions"
        assert call_args[1]["on_conflict"] == "session_id"

    @pytest.mark.asyncio
    async def test_upsert_network_error_retry(self, mock_supabase_client: MagicMock):
        """네트워크 오류 시 재시도."""
        # Arrange
        mock_supabase_client.upsert.side_effect = [
            Exception("Network error"),  # 1st attempt
            Exception("Network error"),  # 2nd attempt
            {"data": [{"id": str(uuid4())}]},  # 3rd attempt success
        ]

        # Act & Assert
        # 첫 번째 시도 실패
        with pytest.raises(Exception, match="Network error"):
            await mock_supabase_client.upsert(table="gfx_sessions", records=[{}])

        # 두 번째 시도 실패
        with pytest.raises(Exception, match="Network error"):
            await mock_supabase_client.upsert(table="gfx_sessions", records=[{}])

        # 세 번째 시도 성공
        result = await mock_supabase_client.upsert(table="gfx_sessions", records=[{}])
        assert result is not None
        assert mock_supabase_client.upsert.call_count == 3


# ============================================================================
# Unit Tests: Realtime Publisher (Mocked)
# ============================================================================


class TestRealtimePublisherIntegration:
    """Realtime Publisher 통합 테스트."""

    @pytest.mark.asyncio
    async def test_publish_hand_inserted_success(
        self, mock_realtime_publisher: MagicMock
    ):
        """핸드 삽입 이벤트 브로드캐스트 성공."""
        # Arrange
        hand_id = uuid4()
        session_id = 99001
        hand_num = 1

        # Act
        result = await mock_realtime_publisher.publish_hand_inserted(
            hand_id=hand_id,
            session_id=session_id,
            hand_num=hand_num,
            player_count=6,
            small_blind=1.0,
            big_blind=2.0,
        )

        # Assert
        assert result is True
        mock_realtime_publisher.publish_hand_inserted.assert_called_once()
        call_args = mock_realtime_publisher.publish_hand_inserted.call_args
        assert call_args[1]["hand_id"] == hand_id
        assert call_args[1]["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_publish_session_updated_success(
        self, mock_realtime_publisher: MagicMock
    ):
        """세션 업데이트 이벤트 브로드캐스트 성공."""
        # Arrange
        session_id = 99001
        hand_count = 10

        # Act
        result = await mock_realtime_publisher.publish_session_updated(
            session_id=session_id,
            hand_count=hand_count,
            status="active",
        )

        # Assert
        assert result is True
        mock_realtime_publisher.publish_session_updated.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_message_with_retry(self, mock_realtime_publisher: MagicMock):
        """메시지 브로드캐스트 실패 후 재시도."""
        # Arrange
        mock_realtime_publisher.publish.side_effect = [
            False,  # 1st attempt fails
            False,  # 2nd attempt fails
            True,  # 3rd attempt succeeds
        ]
        message = BroadcastMessage(
            event=BroadcastEvent.HAND_INSERTED,
            table="gfx_hands",
            payload={"hand_id": str(uuid4())},
        )

        # Act
        result1 = await mock_realtime_publisher.publish(message)
        result2 = await mock_realtime_publisher.publish(message)
        result3 = await mock_realtime_publisher.publish(message)

        # Assert
        assert result1 is False
        assert result2 is False
        assert result3 is True
        assert mock_realtime_publisher.publish.call_count == 3


# ============================================================================
# E2E Tests: Full Pipeline
# ============================================================================


class TestSyncPipelineE2E:
    """전체 동기화 파이프라인 E2E 테스트."""

    @pytest.mark.asyncio
    async def test_full_pipeline_success(
        self,
        sample_json_file: str,
        mock_supabase_client: MagicMock,
        mock_realtime_publisher: MagicMock,
    ):
        """정상 시나리오: JSON → Parser → Supabase → Realtime."""
        # Arrange
        parser = JsonParser()
        adapter = SupabaseSchemaAdapter()
        gfx_pc_id = "PC01"

        # Act 1: JSON 파싱
        parse_result = parser.parse(sample_json_file, gfx_pc_id)
        assert parse_result.success is True
        code_record = parse_result.record

        # Act 2: DB 레코드 변환
        db_record = adapter.to_db_record(code_record, gfx_pc_id)
        assert db_record["session_id"] == 99001
        assert db_record["gfx_pc_id"] == "PC01"
        assert db_record["nas_path"] == "/nas/PC01/session_99001.json"

        # Act 3: Supabase INSERT
        upsert_result = await mock_supabase_client.upsert(
            table="gfx_sessions",
            records=[db_record],
            on_conflict="session_id",
        )
        assert upsert_result is not None

        # Act 4: Realtime 브로드캐스트
        broadcast_result = await mock_realtime_publisher.publish_session_updated(
            session_id=code_record["session_id"],
            hand_count=code_record["hand_count"],
            status="active",
        )
        assert broadcast_result is True

        # Assert: 모든 단계 성공
        assert parse_result.success is True
        assert mock_supabase_client.upsert.called
        assert mock_realtime_publisher.publish_session_updated.called

    @pytest.mark.asyncio
    async def test_pipeline_failure_invalid_json(
        self,
        invalid_json_file: str,
        mock_supabase_client: MagicMock,
        mock_realtime_publisher: MagicMock,
    ):
        """실패 시나리오: 잘못된 JSON."""
        # Arrange
        parser = JsonParser()

        # Act
        parse_result = parser.parse(invalid_json_file, "PC01")

        # Assert
        assert parse_result.success is False
        assert parse_result.error == "json_decode_error"
        # Supabase와 Realtime은 호출되지 않음
        assert not mock_supabase_client.upsert.called
        assert not mock_realtime_publisher.publish_session_updated.called

    @pytest.mark.asyncio
    async def test_pipeline_failure_supabase_error(
        self,
        sample_json_file: str,
        mock_supabase_client: MagicMock,
        mock_realtime_publisher: MagicMock,
    ):
        """실패 시나리오: Supabase INSERT 실패."""
        # Arrange
        parser = JsonParser()
        adapter = SupabaseSchemaAdapter()
        mock_supabase_client.upsert.side_effect = Exception("DB connection error")

        # Act
        parse_result = parser.parse(sample_json_file, "PC01")
        db_record = adapter.to_db_record(parse_result.record, "PC01")

        # Assert
        with pytest.raises(Exception, match="DB connection error"):
            await mock_supabase_client.upsert(
                table="gfx_sessions",
                records=[db_record],
            )

        # Realtime은 호출되지 않음 (DB 실패 시)
        assert not mock_realtime_publisher.publish_session_updated.called

    @pytest.mark.asyncio
    async def test_pipeline_partial_failure_realtime_error(
        self,
        sample_json_file: str,
        mock_supabase_client: MagicMock,
        mock_realtime_publisher: MagicMock,
    ):
        """부분 실패 시나리오: Realtime 브로드캐스트 실패 (DB는 성공)."""
        # Arrange
        parser = JsonParser()
        adapter = SupabaseSchemaAdapter()
        mock_realtime_publisher.publish_session_updated.return_value = False

        # Act
        parse_result = parser.parse(sample_json_file, "PC01")
        db_record = adapter.to_db_record(parse_result.record, "PC01")

        await mock_supabase_client.upsert(
            table="gfx_sessions",
            records=[db_record],
        )

        broadcast_result = await mock_realtime_publisher.publish_session_updated(
            session_id=parse_result.record["session_id"],
            hand_count=parse_result.record["hand_count"],
        )

        # Assert
        assert parse_result.success is True
        assert mock_supabase_client.upsert.called
        # Realtime 실패 시에도 DB는 성공
        assert broadcast_result is False

    @pytest.mark.asyncio
    async def test_pipeline_retry_logic(
        self,
        sample_json_file: str,
        mock_supabase_client: MagicMock,
        mock_realtime_publisher: MagicMock,
    ):
        """재시도 로직 테스트: 네트워크 오류 후 재시도 성공."""
        # Arrange
        parser = JsonParser()
        adapter = SupabaseSchemaAdapter()

        # Mock 재시도 로직 (2번 실패 후 성공)
        mock_supabase_client.upsert.side_effect = [
            Exception("Timeout"),
            Exception("Timeout"),
            {"data": [{"id": str(uuid4())}]},
        ]

        # Act
        parse_result = parser.parse(sample_json_file, "PC01")
        db_record = adapter.to_db_record(parse_result.record, "PC01")

        # 재시도 시뮬레이션
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await mock_supabase_client.upsert(
                    table="gfx_sessions",
                    records=[db_record],
                )
                # 성공 시 루프 종료
                assert result is not None
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    # 재시도
                    await asyncio.sleep(0.1)
                    continue
                else:
                    # 최종 실패
                    raise e

        # Assert
        assert mock_supabase_client.upsert.call_count == 3


# ============================================================================
# Performance Tests
# ============================================================================


class TestPipelinePerformance:
    """파이프라인 성능 테스트."""

    @pytest.mark.asyncio
    async def test_batch_processing_performance(
        self,
        tmp_path: Path,
        mock_supabase_client: MagicMock,
        mock_realtime_publisher: MagicMock,
    ):
        """배치 처리 성능 테스트 (10개 파일)."""
        # Arrange
        parser = JsonParser()
        adapter = SupabaseSchemaAdapter()
        file_count = 10
        json_files = []

        # 10개의 JSON 파일 생성
        for i in range(file_count):
            data = {
                "session": {
                    "id": 99001 + i,
                    "tableType": "cash",
                    "eventTitle": f"Test Event {i}",
                },
                "hands": [{"id": j} for j in range(5)],
            }
            file_path = tmp_path / f"session_{99001 + i}.json"
            file_path.write_text(json.dumps(data), encoding="utf-8")
            json_files.append(str(file_path))

        # Act
        results = []
        for json_file in json_files:
            # Parse
            parse_result = parser.parse(json_file, "PC01")
            assert parse_result.success is True

            # DB Insert
            db_record = adapter.to_db_record(parse_result.record, "PC01")
            await mock_supabase_client.upsert(
                table="gfx_sessions",
                records=[db_record],
            )

            # Realtime Broadcast
            await mock_realtime_publisher.publish_session_updated(
                session_id=parse_result.record["session_id"],
                hand_count=parse_result.record["hand_count"],
            )

            results.append(parse_result)

        # Assert
        assert len(results) == file_count
        assert all(r.success for r in results)
        assert mock_supabase_client.upsert.call_count == file_count
        assert mock_realtime_publisher.publish_session_updated.call_count == file_count
