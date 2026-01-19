"""NAS Sync Agent 설정 모듈.

환경 변수 기반 단일 Settings 클래스.
기존 3개 클래스(AppConfig, SyncAgentSettings, CentralSyncSettings) 통합.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """NAS Sync Agent 설정.

    환경 변수 PREFIX: GFX_SYNC_

    Examples:
        ```bash
        export GFX_SYNC_SUPABASE_URL=https://xxx.supabase.co
        export GFX_SYNC_SUPABASE_SECRET_KEY=sb_secret_xxx
        export GFX_SYNC_NAS_BASE_PATH=/app/data
        ```
    """

    model_config = SettingsConfigDict(
        env_prefix="GFX_SYNC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === NAS 경로 설정 ===
    nas_base_path: str = Field(
        default="/app/data",
        description="NAS 마운트 기본 경로",
    )
    registry_path: str = Field(
        default="config/pc_registry.json",
        description="PC 레지스트리 파일 경로 (nas_base_path 기준 상대 경로)",
    )
    error_folder: str = Field(
        default="_error",
        description="파싱 실패 파일 격리 폴더명",
    )
    file_pattern: str = Field(
        default="*.json",
        description="감시할 파일 패턴",
    )

    # === Supabase 설정 ===
    supabase_url: str = Field(
        default="",
        description="Supabase 프로젝트 URL",
    )
    supabase_secret_key: str = Field(
        default="",
        description="Supabase Secret Key (sb_secret_xxx)",
    )
    supabase_table: str = Field(
        default="gfx_sessions",
        description="동기화 대상 테이블명",
    )
    supabase_timeout: float = Field(
        default=30.0,
        description="Supabase API 타임아웃 (초)",
    )

    # === 폴링 설정 ===
    poll_interval: float = Field(
        default=2.0,
        ge=0.5,
        le=60.0,
        description="파일 감시 폴링 간격 (초)",
    )

    # === 배치 처리 설정 ===
    batch_size: int = Field(
        default=500,
        ge=1,
        le=10000,
        description="배치 최대 크기",
    )
    flush_interval: float = Field(
        default=5.0,
        ge=1.0,
        le=300.0,
        description="배치 자동 플러시 간격 (초)",
    )

    # === 오프라인 큐 설정 ===
    queue_db_path: str = Field(
        default="/app/queue/pending.db",
        description="SQLite DB 파일 경로",
    )
    queue_process_interval: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="오프라인 큐 처리 주기 (초)",
    )
    max_retries: int = Field(
        default=5,
        ge=1,
        le=100,
        description="최대 재시도 횟수",
    )
    max_queue_size: int = Field(
        default=10000,
        ge=100,
        le=1000000,
        description="오프라인 큐 최대 크기",
    )

    # === Rate Limit 대응 ===
    rate_limit_max_retries: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Rate Limit 시 최대 재시도 횟수",
    )
    rate_limit_base_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Rate Limit 지수 백오프 기본 지연 (초)",
    )

    # === 헬스체크 설정 ===
    health_port: int = Field(
        default=8080,
        ge=1024,
        le=65535,
        description="헬스체크 HTTP 서버 포트",
    )
    health_enabled: bool = Field(
        default=True,
        description="헬스체크 서버 활성화 여부",
    )

    # === 로깅 설정 ===
    log_level: str = Field(
        default="INFO",
        description="로그 레벨 (DEBUG, INFO, WARNING, ERROR)",
    )

    @model_validator(mode="after")
    def validate_paths(self) -> Settings:
        """경로 검증."""
        # nas_base_path가 비어있지 않은지 확인
        if not self.nas_base_path:
            raise ValueError("nas_base_path는 필수입니다")
        return self

    @property
    def full_registry_path(self) -> Path:
        """PC 레지스트리 전체 경로."""
        return Path(self.nas_base_path) / self.registry_path

    @property
    def full_error_folder(self) -> Path:
        """오류 폴더 전체 경로."""
        return Path(self.nas_base_path) / self.error_folder

    @property
    def is_supabase_configured(self) -> bool:
        """Supabase 설정 완료 여부."""
        return bool(self.supabase_url and self.supabase_secret_key)

    def get_pc_watch_path(self, pc_id: str) -> Path:
        """PC별 감시 경로 반환.

        Args:
            pc_id: PC 식별자 (예: "PC01")

        Returns:
            감시 경로 (예: /app/data/PC01/hands)
        """
        return Path(self.nas_base_path) / pc_id / "hands"

    def to_dict(self) -> dict[str, Any]:
        """설정을 딕셔너리로 변환 (민감 정보 마스킹)."""
        data = self.model_dump()
        # 민감 정보 마스킹
        if data.get("supabase_secret_key"):
            key = data["supabase_secret_key"]
            data["supabase_secret_key"] = (
                f"{key[:10]}...{key[-4:]}" if len(key) > 14 else "***"
            )
        return data
