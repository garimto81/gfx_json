"""SyncService V4 통합 테스트.

정규화 동기화 파이프라인 테스트.
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
    client.is_connected = True
    return client


@pytest.fixture
def sample_json():
    """샘플 PokerGFX JSON."""
    return {
        "ID": 133877316553960000,
        "CreatedDateTimeUTC": "2024-10-15T10:30:00Z",
        "EventTitle": "Test Game",
        "SoftwareVersion": "PokerGFX 3.2",
        "Type": "FEATURE_TABLE",
        "Hands": [
            {
                "HandNum": 1,
                "Duration": "PT30S",
                "StartDateTimeUTC": "2024-10-15T10:30:05Z",
                "GameVariant": "HOLDEM",
                "GameClass": "FLOP",
                "BetStructure": "NOLIMIT",
                "FlopDrawBlinds": {
                    "SmallBlindAmt": 5000,
                    "BigBlindAmt": 10000,
                },
                "Events": [
                    {"EventType": "FOLD", "PlayerNum": 1, "BetAmt": 0, "Pot": 15000},
                ],
                "Players": [
                    {
                        "PlayerNum": 1,
                        "Name": "PLAYER1",
                        "LongName": "Test Player",
                        "HoleCards": [""],
                        "StartStackAmt": 100000,
                        "EndStackAmt": 100000,
                    },
                ],
            }
        ],
    }


class TestSyncServiceV4:
    """SyncService V4 테스트."""

    @pytest.mark.asyncio
    async def test_sync_json_success(self, mock_client, sample_json, tmp_path):
        """JSON 파일 동기화 성공."""
        from src.sync_agent.core.sync_service_v4 import SyncServiceV4

        # JSON 파일 생성
        json_file = tmp_path / "test.json"
        import json

        json_file.write_text(json.dumps(sample_json))

        service = SyncServiceV4(mock_client)
        result = await service.sync_file(str(json_file), gfx_pc_id="PC01")

        assert result.success is True
        assert result.stats["hands"] == 1
        assert result.stats["players"] == 1
        assert result.stats["events"] == 1

    @pytest.mark.asyncio
    async def test_sync_json_file_not_found(self, mock_client):
        """존재하지 않는 파일."""
        from src.sync_agent.core.sync_service_v4 import SyncServiceV4

        service = SyncServiceV4(mock_client)
        result = await service.sync_file("/nonexistent/file.json", gfx_pc_id="PC01")

        assert result.success is False
        assert "not found" in result.error.lower() or "존재" in result.error

    @pytest.mark.asyncio
    async def test_sync_json_invalid_json(self, mock_client, tmp_path):
        """잘못된 JSON 파일."""
        from src.sync_agent.core.sync_service_v4 import SyncServiceV4

        # 잘못된 JSON 파일 생성
        json_file = tmp_path / "invalid.json"
        json_file.write_text("not valid json {{{")

        service = SyncServiceV4(mock_client)
        result = await service.sync_file(str(json_file), gfx_pc_id="PC01")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_sync_from_content(self, mock_client, sample_json):
        """JSON 문자열에서 직접 동기화."""
        import json

        from src.sync_agent.core.sync_service_v4 import SyncServiceV4

        service = SyncServiceV4(mock_client)
        result = await service.sync_from_content(
            json.dumps(sample_json),
            gfx_pc_id="PC01",
            file_name="test.json",
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_db_error_handling(self, mock_client, sample_json, tmp_path):
        """DB 오류 처리."""
        import json

        from src.sync_agent.core.sync_service_v4 import SyncServiceV4

        # DB 오류 시뮬레이션
        mock_client.upsert = AsyncMock(side_effect=Exception("DB Connection Error"))

        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps(sample_json))

        service = SyncServiceV4(mock_client)
        result = await service.sync_file(str(json_file), gfx_pc_id="PC01")

        assert result.success is False
        assert "DB Connection Error" in result.error


class TestSyncServiceV4Integration:
    """SyncService V4 통합 테스트."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, mock_client, sample_json, tmp_path):
        """전체 파이프라인 테스트."""
        import json

        from src.sync_agent.core.sync_service_v4 import SyncServiceV4

        json_file = tmp_path / "full_test.json"
        json_file.write_text(json.dumps(sample_json))

        service = SyncServiceV4(mock_client)
        result = await service.sync_file(str(json_file), gfx_pc_id="PC01")

        # 5번 upsert 호출 확인 (players, sessions, hands, hand_players, events)
        assert mock_client.upsert.call_count == 5

        # 호출 순서 확인
        calls = mock_client.upsert.call_args_list
        tables = [call.kwargs["table"] for call in calls]

        assert tables[0] == "gfx_players"
        assert tables[1] == "gfx_sessions"
        assert tables[2] == "gfx_hands"
        assert tables[3] == "gfx_hand_players"
        assert tables[4] == "gfx_events"
