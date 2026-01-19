"""Pytest fixtures for GFX Sync Agent tests."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_supabase():
    """Supabase 클라이언트 Mock."""
    client = MagicMock()
    table_mock = MagicMock()
    table_mock.upsert = AsyncMock(return_value={"data": []})
    client.table.return_value = table_mock
    return client


@pytest.fixture
def tmp_watch_dir(tmp_path: Path) -> Path:
    """임시 감시 디렉토리."""
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    return watch_dir


@pytest.fixture
def tmp_queue_db(tmp_path: Path) -> str:
    """임시 큐 DB 경로."""
    return str(tmp_path / "queue.db")
