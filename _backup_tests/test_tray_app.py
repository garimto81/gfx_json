"""TrayApp 테스트."""

import pytest
from PIL import Image

from src.sync_agent.config import AppConfig
from src.sync_agent.tray_app import SyncStatus, TrayApp


@pytest.fixture
def config() -> AppConfig:
    """테스트용 설정."""
    return AppConfig(
        supabase_url="https://test.supabase.co",
        supabase_service_key="test-key",
        gfx_watch_path="C:/test/watch",
        queue_db_path="C:/test/queue.db",
    )


class TestTrayApp:
    """TrayApp 테스트."""

    def test_create_icon_image_gray(self, config: AppConfig) -> None:
        """회색 아이콘 생성."""
        app = TrayApp(config)
        image = app._create_icon_image("gray")
        assert isinstance(image, Image.Image)
        assert image.size == (64, 64)

    def test_create_icon_image_green(self, config: AppConfig) -> None:
        """녹색 아이콘 생성."""
        app = TrayApp(config)
        image = app._create_icon_image("green")
        assert isinstance(image, Image.Image)

    def test_create_icon_image_red(self, config: AppConfig) -> None:
        """빨강 아이콘 생성."""
        app = TrayApp(config)
        image = app._create_icon_image("red")
        assert isinstance(image, Image.Image)

    def test_get_tooltip_idle(self, config: AppConfig) -> None:
        """대기 상태 툴팁."""
        app = TrayApp(config)
        app.status = SyncStatus.IDLE
        assert "대기중" in app._get_tooltip()

    def test_get_tooltip_running(self, config: AppConfig) -> None:
        """실행 상태 툴팁."""
        app = TrayApp(config)
        app.status = SyncStatus.RUNNING
        app.sync_count = 10
        tooltip = app._get_tooltip()
        assert "실행중" in tooltip
        assert "10" in tooltip

    def test_get_tooltip_error(self, config: AppConfig) -> None:
        """오류 상태 툴팁."""
        app = TrayApp(config)
        app.status = SyncStatus.ERROR
        assert "오류" in app._get_tooltip()

    def test_initial_status(self, config: AppConfig) -> None:
        """초기 상태는 IDLE."""
        app = TrayApp(config)
        assert app.status == SyncStatus.IDLE

    def test_create_menu(self, config: AppConfig) -> None:
        """메뉴 생성."""
        app = TrayApp(config)
        menu = app._create_menu()
        assert menu is not None


class TestAppConfig:
    """AppConfig 테스트."""

    def test_is_configured_true(self) -> None:
        """설정 완료 상태."""
        config = AppConfig(
            supabase_url="https://test.supabase.co",
            supabase_service_key="test-key",
        )
        assert config.is_configured() is True

    def test_is_configured_false_no_url(self) -> None:
        """URL 없음."""
        config = AppConfig(supabase_service_key="test-key")
        assert config.is_configured() is False

    def test_is_configured_false_no_key(self) -> None:
        """Key 없음."""
        config = AppConfig(supabase_url="https://test.supabase.co")
        assert config.is_configured() is False

    def test_to_settings(self) -> None:
        """SyncAgentSettings 변환."""
        config = AppConfig(
            supabase_url="https://test.supabase.co",
            supabase_service_key="test-key",
            batch_size=100,
        )
        settings = config.to_settings()
        assert settings.supabase_url == "https://test.supabase.co"
        assert settings.supabase_service_key == "test-key"
        assert settings.batch_size == 100

    def test_save_and_load(self, tmp_path, monkeypatch) -> None:
        """저장 및 로드."""
        # 임시 설정 디렉토리 사용
        monkeypatch.setattr(
            "src.sync_agent.config.get_config_dir",
            lambda: tmp_path,
        )

        config = AppConfig(
            supabase_url="https://test.supabase.co",
            supabase_service_key="test-key",
            batch_size=200,
        )
        config.save()

        loaded = AppConfig.load()
        assert loaded.supabase_url == "https://test.supabase.co"
        assert loaded.supabase_service_key == "test-key"
        assert loaded.batch_size == 200
