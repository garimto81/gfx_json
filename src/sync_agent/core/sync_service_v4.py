"""SyncService V4 - 정규화 동기화 서비스.

JSON → 정규화 테이블 동기화.
TransformationPipeline + UnitOfWork 통합.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.sync_agent.db.supabase_client import SupabaseClient
from src.sync_agent.repositories.unit_of_work import UnitOfWork
from src.sync_agent.transformers.pipeline import TransformationPipeline

logger = logging.getLogger(__name__)


@dataclass
class SyncResultV4:
    """V4 동기화 결과.

    Attributes:
        success: 성공 여부
        error: 에러 메시지 (실패 시)
        stats: 저장된 건수 통계
        session_id: 동기화된 세션 ID
    """

    success: bool
    error: str | None = None
    stats: dict[str, int] = field(default_factory=dict)
    session_id: int | None = None


class SyncServiceV4:
    """정규화 동기화 서비스.

    JSON 파일을 파싱하여 7개 정규화 테이블에 저장.

    변환 흐름:
    JSON File → TransformationPipeline → NormalizedData → UnitOfWork → DB

    Examples:
        ```python
        service = SyncServiceV4(supabase_client)

        # 파일에서 동기화
        result = await service.sync_file("/path/to/file.json", gfx_pc_id="PC01")

        # 문자열에서 동기화
        result = await service.sync_from_content(
            json_content, gfx_pc_id="PC01", file_name="test.json"
        )
        ```
    """

    def __init__(
        self,
        client: SupabaseClient,
        pipeline: TransformationPipeline | None = None,
    ) -> None:
        """초기화.

        Args:
            client: SupabaseClient
            pipeline: TransformationPipeline (기본 생성)
        """
        self.client = client
        self.pipeline = pipeline or TransformationPipeline()
        self.uow = UnitOfWork(client)

    async def sync_file(
        self,
        file_path: str,
        gfx_pc_id: str,
    ) -> SyncResultV4:
        """파일에서 동기화.

        Args:
            file_path: JSON 파일 경로
            gfx_pc_id: GFX PC 식별자

        Returns:
            SyncResultV4
        """
        path = Path(file_path)

        # 파일 존재 확인
        if not path.exists():
            logger.error(f"파일 없음: {file_path}")
            return SyncResultV4(
                success=False, error=f"파일이 존재하지 않습니다: {file_path}"
            )

        try:
            # 파일 읽기
            content = path.read_text(encoding="utf-8")

            # 파일 해시 생성
            file_hash = hashlib.sha256(content.encode()).hexdigest()

            return await self.sync_from_content(
                content=content,
                gfx_pc_id=gfx_pc_id,
                file_name=path.name,
                file_hash=file_hash,
            )

        except UnicodeDecodeError as e:
            logger.error(f"인코딩 오류: {file_path}, {e}")
            return SyncResultV4(success=False, error=f"인코딩 오류: {e}")

        except Exception as e:
            logger.error(f"파일 읽기 실패: {file_path}, {e}")
            return SyncResultV4(success=False, error=str(e))

    async def sync_from_content(
        self,
        content: str,
        gfx_pc_id: str,
        file_name: str,
        file_hash: str | None = None,
    ) -> SyncResultV4:
        """JSON 문자열에서 동기화.

        Args:
            content: JSON 문자열
            gfx_pc_id: GFX PC 식별자
            file_name: 파일명
            file_hash: 파일 해시 (없으면 생성)

        Returns:
            SyncResultV4
        """
        # 해시 생성 (없으면)
        if not file_hash:
            file_hash = hashlib.sha256(content.encode()).hexdigest()

        try:
            # JSON 파싱
            json_data = json.loads(content)

        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            return SyncResultV4(success=False, error=f"JSON 파싱 오류: {e}")

        # 검증
        errors = self.pipeline.validate(json_data)
        if errors:
            logger.warning(f"JSON 검증 경고: {errors}")

        try:
            # 변환
            normalized = self.pipeline.transform(
                json_data=json_data,
                gfx_pc_id=gfx_pc_id,
                file_hash=file_hash,
                file_name=file_name,
            )

            # 저장
            save_result = await self.uow.save_normalized(normalized)

            if save_result.success:
                logger.info(
                    f"[{gfx_pc_id}] 동기화 완료: session={normalized.session.session_id}, "
                    f"stats={save_result.stats}"
                )
                return SyncResultV4(
                    success=True,
                    stats=save_result.stats,
                    session_id=normalized.session.session_id,
                )
            else:
                return SyncResultV4(
                    success=False,
                    error=save_result.error,
                    stats=save_result.stats,
                )

        except Exception as e:
            logger.error(f"[{gfx_pc_id}] 동기화 실패: {e}")
            return SyncResultV4(success=False, error=str(e))

    async def sync_from_dict(
        self,
        json_data: dict[str, Any],
        gfx_pc_id: str,
        file_name: str,
        file_hash: str,
    ) -> SyncResultV4:
        """딕셔너리에서 동기화.

        Args:
            json_data: JSON 딕셔너리
            gfx_pc_id: GFX PC 식별자
            file_name: 파일명
            file_hash: 파일 해시

        Returns:
            SyncResultV4
        """
        try:
            # 변환
            normalized = self.pipeline.transform(
                json_data=json_data,
                gfx_pc_id=gfx_pc_id,
                file_hash=file_hash,
                file_name=file_name,
            )

            # 저장
            save_result = await self.uow.save_normalized(normalized)

            if save_result.success:
                return SyncResultV4(
                    success=True,
                    stats=save_result.stats,
                    session_id=normalized.session.session_id,
                )
            else:
                return SyncResultV4(
                    success=False,
                    error=save_result.error,
                    stats=save_result.stats,
                )

        except Exception as e:
            logger.error(f"[{gfx_pc_id}] 동기화 실패: {e}")
            return SyncResultV4(success=False, error=str(e))
