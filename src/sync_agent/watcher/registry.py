"""PC 레지스트리 관리 모듈.

NAS의 pc_registry.json 파일을 읽고 관리.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PCInfo:
    """GFX PC 정보."""

    pc_id: str
    watch_path: Path
    enabled: bool = True
    description: str | None = None


class PCRegistry:
    """PC 레지스트리 관리.

    NAS의 pc_registry.json 파일에서 PC 목록을 로드하고 관리합니다.

    Examples:
        ```python
        registry = PCRegistry(
            base_path="/app/data",
            registry_file="config/pc_registry.json",
        )

        # 레지스트리 로드
        pcs = registry.load()

        # 활성화된 PC 조회
        for pc in registry.get_enabled_pcs():
            print(f"{pc.pc_id}: {pc.watch_path}")

        # 변경 감지 및 리로드
        if registry.reload():
            print("레지스트리가 변경되었습니다")
        ```

    Registry JSON Format:
        ```json
        {
            "pcs": [
                {
                    "id": "PC01",
                    "watch_path": "PC01/hands",
                    "enabled": true,
                    "description": "Main GFX PC"
                }
            ]
        }
        ```
    """

    def __init__(
        self,
        base_path: str,
        registry_file: str = "config/pc_registry.json",
    ) -> None:
        """초기화.

        Args:
            base_path: NAS 기본 경로
            registry_file: 레지스트리 파일 경로 (base_path 기준 상대 경로)
        """
        self.base_path = Path(base_path)
        self.registry_file = registry_file
        self._pcs: dict[str, PCInfo] = {}
        self._last_mtime: float = 0

    @property
    def registry_path(self) -> Path:
        """레지스트리 파일 전체 경로."""
        return self.base_path / self.registry_file

    def load(self) -> dict[str, PCInfo]:
        """레지스트리 파일 로드.

        Returns:
            활성화된 PC 딕셔너리 {pc_id: PCInfo}
        """
        if not self.registry_path.exists():
            logger.warning(f"PC 레지스트리 없음: {self.registry_path}")
            return {}

        try:
            content = self.registry_path.read_text(encoding="utf-8")
            data = json.loads(content)
            self._last_mtime = self.registry_path.stat().st_mtime

            self._pcs = {}
            for pc_data in data.get("pcs", []):
                pc_id = pc_data.get("id")
                enabled = pc_data.get("enabled", True)

                if not pc_id:
                    logger.warning(f"PC ID 누락: {pc_data}")
                    continue

                if not enabled:
                    continue

                watch_path_str = pc_data.get("watch_path", f"{pc_id}/hands")
                watch_path = self.base_path / watch_path_str

                self._pcs[pc_id] = PCInfo(
                    pc_id=pc_id,
                    watch_path=watch_path,
                    enabled=enabled,
                    description=pc_data.get("description"),
                )

            logger.info(f"PC 레지스트리 로드: {len(self._pcs)}개 활성화")
            return self._pcs

        except json.JSONDecodeError as e:
            logger.error(f"PC 레지스트리 JSON 파싱 오류: {e}")
            return {}
        except OSError as e:
            logger.error(f"PC 레지스트리 읽기 오류: {e}")
            return {}

    def reload(self) -> bool:
        """레지스트리 리로드 (변경 시).

        Returns:
            변경 여부
        """
        if not self.registry_path.exists():
            return False

        try:
            current_mtime = self.registry_path.stat().st_mtime
            if current_mtime <= self._last_mtime:
                return False

            old_pc_ids = set(self._pcs.keys())
            self.load()
            new_pc_ids = set(self._pcs.keys())

            added = new_pc_ids - old_pc_ids
            removed = old_pc_ids - new_pc_ids

            if added:
                logger.info(f"PC 추가됨: {added}")
            if removed:
                logger.info(f"PC 제거됨: {removed}")

            return True

        except Exception as e:
            logger.error(f"레지스트리 리로드 오류: {e}")
            return False

    def get_enabled_pcs(self) -> list[PCInfo]:
        """활성화된 PC 목록 조회.

        Returns:
            활성화된 PCInfo 리스트
        """
        return [pc for pc in self._pcs.values() if pc.enabled]

    def get_pc_ids(self) -> list[str]:
        """활성화된 PC ID 목록.

        Returns:
            PC ID 리스트
        """
        return list(self._pcs.keys())

    def get_watch_paths(self) -> dict[str, Path]:
        """PC별 감시 경로 조회.

        Returns:
            {pc_id: watch_path} 딕셔너리
        """
        return {pc.pc_id: pc.watch_path for pc in self._pcs.values()}

    def get_pc(self, pc_id: str) -> PCInfo | None:
        """특정 PC 정보 조회.

        Args:
            pc_id: PC 식별자

        Returns:
            PCInfo 또는 None
        """
        return self._pcs.get(pc_id)

    def has_changes(self) -> bool:
        """파일 변경 여부 확인 (mtime 기반).

        Returns:
            변경 여부
        """
        if not self.registry_path.exists():
            return False

        try:
            current_mtime = self.registry_path.stat().st_mtime
            return current_mtime > self._last_mtime
        except OSError:
            return False
