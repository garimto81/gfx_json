"""Settings 클래스 단위 테스트."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.sync_agent.config.settings import Settings


class TestSettings:
    """Settings 기본 동작 테스트."""

    def test_default_values(self) -> None:
        """기본값 확인."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        assert settings.nas_base_path == "/app/data"
        assert settings.poll_interval == 2.0
        assert settings.batch_size == 500
        assert settings.flush_interval == 5.0
        assert settings.max_retries == 5
        assert settings.health_port == 8080

    def test_env_prefix(self) -> None:
        """환경 변수 PREFIX (GFX_SYNC_) 확인."""
        env = {
            "GFX_SYNC_NAS_BASE_PATH": "/custom/path",
            "GFX_SYNC_POLL_INTERVAL": "3.5",
            "GFX_SYNC_BATCH_SIZE": "1000",
            "GFX_SYNC_SUPABASE_URL": "https://test.supabase.co",
            "GFX_SYNC_SUPABASE_SECRET_KEY": "sb_secret_test123",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()

        assert settings.nas_base_path == "/custom/path"
        assert settings.poll_interval == 3.5
        assert settings.batch_size == 1000
        assert settings.supabase_url == "https://test.supabase.co"
        assert settings.supabase_secret_key == "sb_secret_test123"

    def test_poll_interval_bounds(self) -> None:
        """poll_interval 범위 검증 (0.5 ~ 60.0)."""
        # 최소값
        with patch.dict(os.environ, {"GFX_SYNC_POLL_INTERVAL": "0.5"}, clear=True):
            settings = Settings()
            assert settings.poll_interval == 0.5

        # 최대값
        with patch.dict(os.environ, {"GFX_SYNC_POLL_INTERVAL": "60.0"}, clear=True):
            settings = Settings()
            assert settings.poll_interval == 60.0

        # 범위 초과
        with patch.dict(os.environ, {"GFX_SYNC_POLL_INTERVAL": "100.0"}, clear=True):
            with pytest.raises(ValueError):
                Settings()

    def test_batch_size_bounds(self) -> None:
        """batch_size 범위 검증 (1 ~ 10000)."""
        with patch.dict(os.environ, {"GFX_SYNC_BATCH_SIZE": "0"}, clear=True):
            with pytest.raises(ValueError):
                Settings()

        with patch.dict(os.environ, {"GFX_SYNC_BATCH_SIZE": "10001"}, clear=True):
            with pytest.raises(ValueError):
                Settings()


class TestSettingsProperties:
    """Settings 프로퍼티 테스트."""

    def test_full_registry_path(self) -> None:
        """full_registry_path 프로퍼티."""
        env = {"GFX_SYNC_NAS_BASE_PATH": "/app/data"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()

        assert settings.full_registry_path == Path("/app/data/config/pc_registry.json")

    def test_full_error_folder(self) -> None:
        """full_error_folder 프로퍼티."""
        env = {"GFX_SYNC_NAS_BASE_PATH": "/app/data"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()

        assert settings.full_error_folder == Path("/app/data/_error")

    def test_is_supabase_configured_false(self) -> None:
        """Supabase 미설정 시 False."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)

        assert settings.is_supabase_configured is False

    def test_is_supabase_configured_true(self) -> None:
        """Supabase 설정 시 True."""
        env = {
            "GFX_SYNC_SUPABASE_URL": "https://test.supabase.co",
            "GFX_SYNC_SUPABASE_SECRET_KEY": "sb_secret_test",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()

        assert settings.is_supabase_configured is True

    def test_get_pc_watch_path(self) -> None:
        """PC별 감시 경로 생성."""
        env = {"GFX_SYNC_NAS_BASE_PATH": "/app/data"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()

        assert settings.get_pc_watch_path("PC01") == Path("/app/data/PC01/hands")
        assert settings.get_pc_watch_path("PC02") == Path("/app/data/PC02/hands")


class TestSettingsSecurity:
    """Settings 보안 관련 테스트."""

    def test_to_dict_masks_secret_key(self) -> None:
        """to_dict()에서 secret_key 마스킹."""
        env = {
            "GFX_SYNC_SUPABASE_URL": "https://test.supabase.co",
            "GFX_SYNC_SUPABASE_SECRET_KEY": "sb_secret_very_long_key_12345678",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()

        data = settings.to_dict()
        # 마스킹 형식: 앞 10자...뒤 4자
        assert "..." in data["supabase_secret_key"]
        assert data["supabase_secret_key"].startswith("sb_secret_")
        assert data["supabase_secret_key"].endswith("5678")
        assert "very_long_key" not in data["supabase_secret_key"]

    def test_to_dict_empty_secret_key(self) -> None:
        """비어있는 secret_key 처리."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)

        data = settings.to_dict()
        assert data["supabase_secret_key"] == ""
