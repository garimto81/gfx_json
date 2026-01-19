"""설정 관리."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_config_dir() -> Path:
    """설정 디렉토리 경로 반환.

    Windows: %APPDATA%/GFX_Sync
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.config")

    config_dir = Path(base) / "GFX_Sync"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """설정 파일 경로 반환."""
    return get_config_dir() / "config.json"


@dataclass
class AppConfig:
    """앱 설정 (파일 기반).

    JSON 파일에 저장/로드됩니다.
    위치: %APPDATA%/GFX_Sync/config.json
    """

    # Supabase
    supabase_url: str = ""
    # 신규 키 (sb_secret_...) 또는 레거시 키 (JWT) 모두 지원
    supabase_secret_key: str = ""
    # 레거시 호환성 (마이그레이션 기간)
    supabase_service_key: str = ""  # deprecated, use supabase_secret_key

    # 경로
    gfx_watch_path: str = "C:/GFX/output"
    queue_db_path: str = "C:/GFX/sync_queue/pending.db"

    # 배치 설정
    batch_size: int = 500
    flush_interval: float = 5.0

    # 큐 설정
    queue_process_interval: int = 60
    max_retries: int = 5

    def save(self) -> None:
        """설정을 파일에 저장."""
        config_path = get_config_path()
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls) -> "AppConfig":
        """파일에서 설정 로드."""
        config_path = get_config_path()

        if not config_path.exists():
            return cls()

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        except (json.JSONDecodeError, TypeError):
            return cls()

    def get_api_key(self) -> str:
        """API 키 반환 (신규 키 우선, 레거시 fallback)."""
        return self.supabase_secret_key or self.supabase_service_key

    def is_configured(self) -> bool:
        """필수 설정이 완료되었는지 확인."""
        return bool(self.supabase_url and self.get_api_key())

    def to_settings(self) -> "SyncAgentSettings":
        """SyncAgentSettings로 변환."""
        return SyncAgentSettings(
            supabase_url=self.supabase_url,
            supabase_secret_key=self.get_api_key(),
            gfx_watch_path=self.gfx_watch_path,
            queue_db_path=self.queue_db_path,
            batch_size=self.batch_size,
            flush_interval=self.flush_interval,
            queue_process_interval=self.queue_process_interval,
            max_retries=self.max_retries,
        )


class SyncAgentSettings(BaseSettings):
    """SyncAgent 설정.

    환경 변수 prefix: GFX_SYNC_
    """

    model_config = SettingsConfigDict(
        env_prefix="GFX_SYNC_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Supabase 연결
    # URL: https://<project-ref>.supabase.co
    supabase_url: str = Field(default="")

    # 신규 API 키 (sb_secret_...)
    # - 서버 사이드 앱 전용
    # - RLS 우회하여 모든 데이터 접근 가능
    # - 위치: Supabase Dashboard > Settings > API Keys > Secret key
    supabase_secret_key: str = Field(default="")

    # 레거시 키 (JWT 형식) - 마이그레이션 기간 동안 fallback
    supabase_service_key: str = Field(default="")

    def get_api_key(self) -> str:
        """API 키 반환 (신규 키 우선, 레거시 fallback)."""
        return self.supabase_secret_key or self.supabase_service_key

    # 감시 경로
    gfx_watch_path: str = Field(default="C:/GFX/output")

    # 배치 처리 설정
    batch_size: int = Field(default=500)
    flush_interval: float = Field(default=5.0)

    # 오프라인 큐
    queue_db_path: str = Field(default="C:/GFX/sync_queue/pending.db")
    queue_process_interval: int = Field(default=60)
    max_retries: int = Field(default=5)


class CentralSyncSettings(BaseSettings):
    """NAS 중앙 Sync Agent 설정.

    환경 변수 prefix: GFX_SYNC_
    Docker 환경에서 사용합니다.
    """

    model_config = SettingsConfigDict(
        env_prefix="GFX_SYNC_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # NAS 경로 (Docker 볼륨 마운트 경로)
    nas_base_path: str = Field(default="/app/data")

    # PC 레지스트리 파일 경로
    registry_path: str = Field(default="config/pc_registry.json")

    # Supabase 연결
    supabase_url: str = Field(default="")

    # 신규 API 키 (sb_secret_...)
    supabase_secret_key: str = Field(default="")

    # 레거시 키 (JWT 형식) - 마이그레이션 기간 동안 fallback
    supabase_service_key: str = Field(default="")

    def get_api_key(self) -> str:
        """API 키 반환 (신규 키 우선, 레거시 fallback)."""
        return self.supabase_secret_key or self.supabase_service_key

    # 폴링 설정 (SMB용 - watchfiles는 SMB 미지원)
    poll_interval: float = Field(default=2.0, description="폴링 주기 (초)")

    # 배치 처리 설정
    batch_size: int = Field(default=500)
    flush_interval: float = Field(default=5.0)

    # 오프라인 큐
    queue_db_path: str = Field(default="/app/queue/pending.db")
    queue_process_interval: int = Field(default=60)
    max_retries: int = Field(default=5)

    # 레지스트리 감시
    registry_check_interval: int = Field(
        default=30,
        description="PC 레지스트리 변경 확인 주기 (초)",
    )

    # 오류 파일 격리
    error_folder: str = Field(default="_error")

    def get_registry_full_path(self) -> Path:
        """PC 레지스트리 전체 경로."""
        return Path(self.nas_base_path) / self.registry_path

    def get_error_folder_path(self) -> Path:
        """오류 파일 격리 폴더 경로."""
        return Path(self.nas_base_path) / self.error_folder
