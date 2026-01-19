"""SupabaseClient 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.sync_agent.db.supabase_client import (
    RateLimitError,
    SupabaseAPIError,
    SupabaseClient,
    UpsertResult,
)


@pytest.fixture
def client():
    """테스트용 SupabaseClient fixture."""
    return SupabaseClient(
        url="https://test.supabase.co",
        secret_key="sb_secret_test123",
        timeout=10.0,
    )


class TestSupabaseClientInit:
    """초기화 테스트."""

    def test_init_strips_trailing_slash(self):
        """URL 끝 슬래시 제거."""
        client = SupabaseClient(
            url="https://test.supabase.co/",
            secret_key="key",
        )
        assert client.url == "https://test.supabase.co"

    def test_init_default_timeout(self):
        """기본 타임아웃 30초."""
        client = SupabaseClient(url="https://test.supabase.co", secret_key="key")
        assert client.timeout == 30.0


class TestSupabaseClientConnect:
    """connect/close 테스트."""

    @pytest.mark.asyncio
    async def test_connect_creates_client(self, client):
        """connect() 호출 시 httpx.AsyncClient 생성."""
        assert client._client is None

        await client.connect()

        assert client._client is not None
        assert isinstance(client._client, httpx.AsyncClient)
        assert client.is_connected is True

        await client.close()

    @pytest.mark.asyncio
    async def test_close_clears_client(self, client):
        """close() 호출 시 클라이언트 정리."""
        await client.connect()
        await client.close()

        assert client._client is None
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_context_manager(self, client):
        """async with 문 지원."""
        async with SupabaseClient(
            url="https://test.supabase.co", secret_key="key"
        ) as c:
            assert c.is_connected is True

        assert c.is_connected is False


class TestSupabaseClientUpsert:
    """upsert 테스트."""

    @pytest.mark.asyncio
    async def test_upsert_success(self, client):
        """성공적인 upsert."""
        await client.connect()

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.headers = {}

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client.upsert(
                table="gfx_sessions",
                records=[{"file_hash": "abc", "data": "test"}],
                on_conflict="file_hash",
            )

        assert result.success is True
        assert result.count == 1
        mock_post.assert_called_once()

        await client.close()

    @pytest.mark.asyncio
    async def test_upsert_empty_records(self, client):
        """빈 레코드 리스트."""
        await client.connect()

        result = await client.upsert(table="test", records=[])

        assert result.success is True
        assert result.count == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_upsert_rate_limit(self, client):
        """Rate Limit 예외 (HTTP 429)."""
        await client.connect()

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(RateLimitError) as exc_info:
                await client.upsert(table="test", records=[{"id": 1}])

        assert exc_info.value.retry_after == 60

        await client.close()

    @pytest.mark.asyncio
    async def test_upsert_client_error(self, client):
        """클라이언트 오류 (HTTP 400)."""
        await client.connect()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"error": "Invalid request"}'
        mock_response.headers = {}

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(SupabaseAPIError) as exc_info:
                await client.upsert(table="test", records=[{"id": 1}])

        assert exc_info.value.status_code == 400

        await client.close()

    @pytest.mark.asyncio
    async def test_upsert_server_error(self, client):
        """서버 오류 (HTTP 500)."""
        await client.connect()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client.upsert(table="test", records=[{"id": 1}])

        assert result.success is False
        assert "Server error" in result.error

        await client.close()

    @pytest.mark.asyncio
    async def test_upsert_timeout(self, client):
        """타임아웃 처리."""
        await client.connect()

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Connection timeout")

            result = await client.upsert(table="test", records=[{"id": 1}])

        assert result.success is False
        assert result.error == "timeout"

        await client.close()

    @pytest.mark.asyncio
    async def test_upsert_without_connect_raises(self, client):
        """연결 없이 upsert 호출 시 오류."""
        with pytest.raises(RuntimeError, match="연결되지 않음"):
            await client.upsert(table="test", records=[{"id": 1}])


class TestSupabaseClientSelect:
    """select 테스트."""

    @pytest.mark.asyncio
    async def test_select_success(self, client):
        """성공적인 select."""
        await client.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1, "name": "test"}]
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await client.select(table="test", limit=10)

        assert len(result) == 1
        assert result[0]["name"] == "test"

        await client.close()

    @pytest.mark.asyncio
    async def test_select_with_filters(self, client):
        """필터 적용 select."""
        await client.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.select(
                table="test",
                filters={"gfx_pc_id": "PC01"},
            )

        # 필터가 파라미터로 전달되었는지 확인
        call_args = mock_get.call_args
        assert "gfx_pc_id" in call_args.kwargs["params"]

        await client.close()


class TestSupabaseClientDelete:
    """delete 테스트."""

    @pytest.mark.asyncio
    async def test_delete_success(self, client):
        """성공적인 delete."""
        await client.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            client._client, "delete", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = mock_response

            count = await client.delete(table="test", filters={"status": "old"})

        assert count == 2

        await client.close()


class TestSupabaseClientHealthCheck:
    """health_check 테스트."""

    @pytest.mark.asyncio
    async def test_health_check_connected(self, client):
        """연결 상태에서 헬스체크."""
        await client.connect()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await client.health_check()

        assert result is True

        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_not_connected(self, client):
        """미연결 상태에서 헬스체크."""
        result = await client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_error(self, client):
        """헬스체크 오류."""
        await client.connect()

        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.RequestError("Connection refused")

            result = await client.health_check()

        assert result is False

        await client.close()


class TestRateLimitError:
    """RateLimitError 테스트."""

    def test_rate_limit_error_with_retry_after(self):
        """retry_after 포함."""
        error = RateLimitError("Too many requests", retry_after=60)
        assert error.retry_after == 60
        assert "Too many requests" in str(error)

    def test_rate_limit_error_without_retry_after(self):
        """retry_after 미포함."""
        error = RateLimitError()
        assert error.retry_after is None


class TestUpsertResult:
    """UpsertResult 테스트."""

    def test_upsert_result_success(self):
        """성공 결과."""
        result = UpsertResult(success=True, count=5)
        assert result.success is True
        assert result.count == 5
        assert result.error is None

    def test_upsert_result_failure(self):
        """실패 결과."""
        result = UpsertResult(success=False, count=0, error="timeout")
        assert result.success is False
        assert result.error == "timeout"
