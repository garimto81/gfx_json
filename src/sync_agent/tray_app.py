"""System Tray GUI 앱."""

from __future__ import annotations

import asyncio
import logging
import threading
from enum import Enum
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from src.sync_agent.config import AppConfig

logger = logging.getLogger(__name__)


class SyncStatus(Enum):
    """동기화 상태."""

    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class TrayApp:
    """System Tray 앱.

    백그라운드에서 SyncAgent를 실행하고
    트레이 아이콘으로 상태를 표시합니다.
    """

    def __init__(self, config: "AppConfig") -> None:
        """초기화.

        Args:
            config: 앱 설정
        """
        self.config = config
        self.status = SyncStatus.IDLE
        self.sync_count = 0
        self._icon: pystray.Icon | None = None
        self._agent_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._agent = None

    def _create_icon_image(self, color: str = "gray") -> Image.Image:
        """트레이 아이콘 이미지 생성.

        Args:
            color: 아이콘 색상 (gray, green, red)

        Returns:
            PIL Image
        """
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # 색상 매핑
        colors = {
            "gray": "#808080",
            "green": "#00C853",
            "red": "#FF5252",
        }
        fill_color = colors.get(color, "#808080")

        # 원형 아이콘
        margin = 4
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=fill_color,
            outline="#FFFFFF",
            width=2,
        )

        # S 문자 (Sync)
        draw.text(
            (size // 2, size // 2),
            "S",
            fill="#FFFFFF",
            anchor="mm",
        )

        return image

    def _get_status_icon(self) -> Image.Image:
        """현재 상태에 맞는 아이콘 반환."""
        color_map = {
            SyncStatus.IDLE: "gray",
            SyncStatus.RUNNING: "green",
            SyncStatus.ERROR: "red",
        }
        return self._create_icon_image(color_map[self.status])

    def _get_tooltip(self) -> str:
        """현재 상태에 맞는 툴팁 반환."""
        tooltips = {
            SyncStatus.IDLE: "GFX Sync - 대기중",
            SyncStatus.RUNNING: f"GFX Sync - 실행중 ({self.sync_count}건 처리)",
            SyncStatus.ERROR: "GFX Sync - 오류 발생",
        }
        return tooltips[self.status]

    def _create_menu(self) -> pystray.Menu:
        """트레이 메뉴 생성."""
        return pystray.Menu(
            pystray.MenuItem(
                lambda _: self._get_tooltip(),
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "시작",
                self._on_start,
                enabled=lambda _: self.status == SyncStatus.IDLE and self.config.is_configured(),
            ),
            pystray.MenuItem(
                "중지",
                self._on_stop,
                enabled=lambda _: self.status == SyncStatus.RUNNING,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("설정", self._on_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("종료", self._on_quit),
        )

    def _update_icon(self) -> None:
        """아이콘 업데이트."""
        if self._icon:
            self._icon.icon = self._get_status_icon()
            self._icon.title = self._get_tooltip()

    def _on_settings(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """설정 메뉴 클릭."""
        # 실행 중이면 먼저 중지
        if self.status == SyncStatus.RUNNING:
            self._on_stop(icon, item)

        # 설정 다이얼로그 표시 (별도 스레드)
        threading.Thread(target=self._show_settings_dialog, daemon=True).start()

    def _show_settings_dialog(self) -> None:
        """설정 다이얼로그 표시."""
        from src.sync_agent.settings_dialog import show_settings_dialog

        # 다이얼로그 표시
        saved = show_settings_dialog(self.config)

        if saved:
            logger.info("설정 저장됨")
            # 설정 다시 로드
            from src.sync_agent.config import AppConfig
            self.config = AppConfig.load()

    def _on_start(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """시작 메뉴 클릭."""
        if self.status != SyncStatus.IDLE:
            return

        if not self.config.is_configured():
            logger.warning("설정이 완료되지 않았습니다.")
            self._on_settings(icon, item)
            return

        logger.info("동기화 시작")
        self.status = SyncStatus.RUNNING
        self._update_icon()

        # 별도 스레드에서 asyncio 루프 실행
        self._agent_thread = threading.Thread(
            target=self._run_agent,
            daemon=True,
        )
        self._agent_thread.start()

    def _run_agent(self) -> None:
        """SyncAgent 실행 (별도 스레드)."""
        from src.sync_agent.main import SyncAgent

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            settings = self.config.to_settings()
            self._agent = SyncAgent(settings)
            self._loop.run_until_complete(self._agent.start())
        except Exception as e:
            logger.error(f"SyncAgent 오류: {e}")
            self.status = SyncStatus.ERROR
            self._update_icon()
        finally:
            self._loop.close()

    def _on_stop(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """중지 메뉴 클릭."""
        if self.status != SyncStatus.RUNNING:
            return

        logger.info("동기화 중지")

        if self._agent and self._loop:
            # 에이전트 중지
            future = asyncio.run_coroutine_threadsafe(
                self._agent.stop(),
                self._loop,
            )
            try:
                future.result(timeout=5.0)
            except Exception as e:
                logger.error(f"중지 오류: {e}")

        self.status = SyncStatus.IDLE
        self._update_icon()

    def _on_quit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """종료 메뉴 클릭."""
        logger.info("앱 종료")

        # 실행 중이면 먼저 중지
        if self.status == SyncStatus.RUNNING:
            self._on_stop(icon, item)

        icon.stop()

    def run(self) -> None:
        """앱 실행."""
        logger.info("GFX Sync Tray 앱 시작")

        # 설정이 없으면 설정 다이얼로그 먼저 표시
        if not self.config.is_configured():
            logger.info("초기 설정 필요")
            self._show_settings_dialog()

            # 다시 로드
            from src.sync_agent.config import AppConfig
            self.config = AppConfig.load()

        self._icon = pystray.Icon(
            name="GFX Sync",
            icon=self._get_status_icon(),
            title=self._get_tooltip(),
            menu=self._create_menu(),
        )

        self._icon.run()


def run_tray_app() -> None:
    """Tray 앱 실행."""
    from src.sync_agent.config import AppConfig

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = AppConfig.load()
    app = TrayApp(config)
    app.run()
