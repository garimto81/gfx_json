"""JSON 파싱 모듈.

PokerGFX JSON 파일 파싱 및 file_hash 생성.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """파싱 오류."""

    def __init__(self, message: str, file_path: str | None = None):
        super().__init__(message)
        self.file_path = file_path


@dataclass
class ParseResult:
    """파싱 결과."""

    success: bool
    record: dict[str, Any] | None = None
    error: str | None = None
    file_path: str | None = None


@dataclass
class JsonParser:
    """PokerGFX JSON 파서.

    기능:
    - JSON 파일 파싱
    - file_hash 생성 (SHA-256)
    - 메타데이터 추출 (session_id, table_type 등)
    - gfx_pc_id 추가

    Examples:
        ```python
        parser = JsonParser()

        result = parser.parse("/path/to/file.json", gfx_pc_id="PC01")
        if result.success:
            record = result.record
            # {'gfx_pc_id': 'PC01', 'file_hash': 'abc...', 'session_id': 1, ...}
        ```
    """

    encoding: str = "utf-8"
    hash_algorithm: str = "sha256"

    def parse(self, file_path: str, gfx_pc_id: str) -> ParseResult:
        """JSON 파일 파싱.

        Args:
            file_path: JSON 파일 경로
            gfx_pc_id: GFX PC 식별자

        Returns:
            ParseResult
        """
        path = Path(file_path)

        # 파일 존재 확인
        if not path.exists():
            return ParseResult(
                success=False,
                error="file_not_found",
                file_path=file_path,
            )

        try:
            # 파일 읽기
            content = path.read_text(encoding=self.encoding)

            # JSON 파싱
            data = json.loads(content)

            # file_hash 생성
            file_hash = self._generate_hash(content)

            # 레코드 생성
            record = self._build_record(data, path, gfx_pc_id, file_hash)

            return ParseResult(
                success=True,
                record=record,
                file_path=file_path,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"JSON 파싱 오류 ({file_path}): {e}")
            return ParseResult(
                success=False,
                error="json_decode_error",
                file_path=file_path,
            )

        except UnicodeDecodeError as e:
            logger.warning(f"인코딩 오류 ({file_path}): {e}")
            return ParseResult(
                success=False,
                error="encoding_error",
                file_path=file_path,
            )

        except Exception as e:
            logger.error(f"파싱 오류 ({file_path}): {e}")
            return ParseResult(
                success=False,
                error=str(e),
                file_path=file_path,
            )

    def parse_content(
        self, content: str, file_name: str, gfx_pc_id: str
    ) -> ParseResult:
        """문자열 내용 파싱.

        Args:
            content: JSON 문자열
            file_name: 파일명 (메타데이터용)
            gfx_pc_id: GFX PC 식별자

        Returns:
            ParseResult
        """
        try:
            data = json.loads(content)
            file_hash = self._generate_hash(content)

            record = {
                "file_hash": file_hash,
                "file_name": file_name,
                "session_id": self._extract_session_id(data, file_name),
                "raw_json": data,
                # 내부용 메타데이터 (DB 컬럼 없음)
                "_gfx_pc_id": gfx_pc_id,
            }

            # Optional 필드 - NULL이 아닌 경우만 추가
            table_type = self._extract_table_type(data)
            record["table_type"] = table_type  # 항상 저장 (기본값 UNKNOWN)

            event_title = self._extract_event_title(data)
            if event_title is not None:  # 빈 문자열도 저장
                record["event_title"] = event_title

            software_version = self._extract_software_version(data)
            if software_version is not None:  # 빈 문자열도 저장
                record["software_version"] = software_version

            hand_count = self._count_hands(data)
            if hand_count:
                record["hand_count"] = hand_count

            # player_count 추출 (Hands[].Players에서)
            player_count = self._extract_player_count(data)
            if player_count:
                record["player_count"] = player_count

            payouts = self._extract_payouts(data)
            if payouts:
                record["payouts"] = payouts

            return ParseResult(success=True, record=record)

        except json.JSONDecodeError:
            return ParseResult(success=False, error="json_decode_error")

    def _generate_hash(self, content: str) -> str:
        """파일 내용 기반 해시 생성.

        Args:
            content: 파일 내용

        Returns:
            SHA-256 해시 (hex)
        """
        if self.hash_algorithm == "sha256":
            return hashlib.sha256(content.encode()).hexdigest()
        elif self.hash_algorithm == "md5":
            return hashlib.md5(content.encode()).hexdigest()
        else:
            return hashlib.sha256(content.encode()).hexdigest()

    def _build_record(
        self,
        data: dict[str, Any],
        path: Path,
        gfx_pc_id: str,
        file_hash: str,
    ) -> dict[str, Any]:
        """Supabase 레코드 생성.

        Args:
            data: 파싱된 JSON 데이터
            path: 파일 경로
            gfx_pc_id: GFX PC 식별자
            file_hash: 파일 해시

        Returns:
            Supabase 레코드
        """
        record = {
            "file_hash": file_hash,
            "file_name": path.name,
            "nas_path": f"/nas/{gfx_pc_id}/{path.name}",  # gfx_pc_id를 nas_path에 포함
            "session_id": self._extract_session_id(data, path.name),
            "raw_json": data,
            # 내부용 메타데이터 (DB 컬럼 없음)
            "_gfx_pc_id": gfx_pc_id,
        }

        # Optional 필드 - NULL이 아닌 경우만 추가
        table_type = self._extract_table_type(data)
        record["table_type"] = table_type  # 항상 저장 (기본값 UNKNOWN)

        event_title = self._extract_event_title(data)
        if event_title is not None:  # 빈 문자열도 저장
            record["event_title"] = event_title

        software_version = self._extract_software_version(data)
        if software_version is not None:  # 빈 문자열도 저장
            record["software_version"] = software_version

        hand_count = self._count_hands(data)
        if hand_count:
            record["hand_count"] = hand_count

        # player_count 추출 (Hands[].Players에서)
        player_count = self._extract_player_count(data)
        if player_count:
            record["player_count"] = player_count

        # payouts 컬럼은 DB에 있음
        payouts = self._extract_payouts(data)
        if payouts:
            record["payouts"] = payouts

        return record

    def _extract_session_id(
        self, data: dict[str, Any], file_name: str = ""
    ) -> int | None:
        """session_id 추출.

        다양한 형식 지원 (우선순위):
        1. {"ID": 123}              # PascalCase (문서 기준)
        2. {"session_id": 123}      # snake_case
        3. {"session": {"id": 123}} # nested
        4. {"id": 123}              # lowercase
        5. 파일명 GameID 추출       # fallback (PGFX_live_data_export GameID=123.json)
        """
        # PascalCase (문서 기준 - 02-GFX-JSON-DB.md)
        if "ID" in data:
            return int(data["ID"])

        # snake_case
        if "session_id" in data:
            return int(data["session_id"])

        # nested
        if "session" in data and isinstance(data["session"], dict):
            if "id" in data["session"]:
                return int(data["session"]["id"])

        # lowercase
        if "id" in data:
            return int(data["id"])

        # 파일명에서 GameID 추출 (fallback)
        if file_name:
            match = re.search(r"GameID=(\d+)", file_name)
            if match:
                return int(match.group(1))

        return None

    # Supabase table_type ENUM 값 매핑
    TABLE_TYPE_MAPPING: dict[str, str] = field(
        default_factory=lambda: {
            # 정확한 매칭
            "feature_table": "FEATURE_TABLE",
            "main_table": "MAIN_TABLE",
            "final_table": "FINAL_TABLE",
            "side_table": "SIDE_TABLE",
            "unknown": "UNKNOWN",
            # 일반적인 값 매핑
            "feature": "FEATURE_TABLE",
            "main": "MAIN_TABLE",
            "final": "FINAL_TABLE",
            "side": "SIDE_TABLE",
            "cash": "MAIN_TABLE",  # cash -> MAIN_TABLE
            "tournament": "MAIN_TABLE",
        }
    )

    def _extract_table_type(self, data: dict[str, Any]) -> str | None:
        """table_type 추출.

        다양한 형식 지원 (우선순위):
        - {"Type": "FEATURE_TABLE"}   # PascalCase (문서 기준)
        - {"table_type": "cash"}
        - {"tableType": "cash"}
        - {"session": {"Type": "..."}}
        - {"session": {"table_type": "..."}}
        - {"session": {"tableType": "..."}}

        Supabase ENUM 타입으로 매핑:
        - FEATURE_TABLE, MAIN_TABLE, FINAL_TABLE, SIDE_TABLE, UNKNOWN
        """
        value = None

        # PascalCase (문서 기준 - 02-GFX-JSON-DB.md)
        if "Type" in data:
            value = str(data["Type"])
        # snake_case
        elif "table_type" in data:
            value = str(data["table_type"])
        # camelCase
        elif "tableType" in data:
            value = str(data["tableType"])
        # nested
        elif "session" in data and isinstance(data["session"], dict):
            if "Type" in data["session"]:
                value = str(data["session"]["Type"])
            elif "table_type" in data["session"]:
                value = str(data["session"]["table_type"])
            elif "tableType" in data["session"]:
                value = str(data["session"]["tableType"])

        if not value:
            return "UNKNOWN"  # 기본값

        # ENUM 매핑
        normalized = value.lower().strip()
        return self.TABLE_TYPE_MAPPING.get(normalized, "UNKNOWN")

    def _extract_event_title(self, data: dict[str, Any]) -> str | None:
        """event_title 추출.

        다양한 형식 지원 (우선순위):
        - {"EventTitle": "..."}       # PascalCase (문서 기준)
        - {"event_title": "..."}
        - {"eventTitle": "..."}
        - {"session": {"EventTitle": "..."}}
        - {"session": {"event_title": "..."}}
        - {"session": {"eventTitle": "..."}}
        """
        # PascalCase (문서 기준 - 02-GFX-JSON-DB.md)
        if "EventTitle" in data:
            return str(data["EventTitle"])

        if "event_title" in data:
            return str(data["event_title"])

        if "eventTitle" in data:
            return str(data["eventTitle"])

        if "session" in data and isinstance(data["session"], dict):
            if "EventTitle" in data["session"]:
                return str(data["session"]["EventTitle"])
            if "event_title" in data["session"]:
                return str(data["session"]["event_title"])
            if "eventTitle" in data["session"]:
                return str(data["session"]["eventTitle"])

        return None

    def _extract_software_version(self, data: dict[str, Any]) -> str | None:
        """software_version 추출.

        다양한 형식 지원 (우선순위):
        - {"SoftwareVersion": "..."}  # PascalCase (문서 기준)
        - {"software_version": "..."}
        - {"softwareVersion": "..."}
        - {"session": {"SoftwareVersion": "..."}}
        - {"session": {"software_version": "..."}}
        - {"session": {"softwareVersion": "..."}}
        """
        # PascalCase (문서 기준 - 02-GFX-JSON-DB.md)
        if "SoftwareVersion" in data:
            return str(data["SoftwareVersion"])

        if "software_version" in data:
            return str(data["software_version"])

        if "softwareVersion" in data:
            return str(data["softwareVersion"])

        if "session" in data and isinstance(data["session"], dict):
            if "SoftwareVersion" in data["session"]:
                return str(data["session"]["SoftwareVersion"])
            if "software_version" in data["session"]:
                return str(data["session"]["software_version"])
            if "softwareVersion" in data["session"]:
                return str(data["session"]["softwareVersion"])

        return None

    def _extract_created_at(self, data: dict[str, Any]) -> str | None:
        """생성 시간 추출.

        다양한 형식 지원 (우선순위):
        - {"CreatedDateTimeUTC": "2024-01-01T00:00:00Z"}  # PascalCase (문서 기준)
        - {"created_at": "..."}
        - {"created_datetime_utc": "..."}
        - {"timestamp": "..."}
        - {"createdAt": "..."}
        """
        # PascalCase 우선 (문서 기준 - 02-GFX-JSON-DB.md)
        for key in [
            "CreatedDateTimeUTC",
            "created_at",
            "created_datetime_utc",
            "timestamp",
            "createdAt",
        ]:
            if key in data and data[key]:
                return str(data[key])

        return None

    def _count_hands(self, data: dict[str, Any]) -> int:
        """핸드 수 계산.

        다양한 형식 지원 (우선순위):
        - {"Hands": [...]}     # PascalCase (문서 기준)
        - {"hands": [...]}
        - {"hand_count": 10}
        - {"handCount": 10}
        """
        # PascalCase (문서 기준 - 02-GFX-JSON-DB.md)
        if "Hands" in data and isinstance(data["Hands"], list):
            return len(data["Hands"])

        if "hands" in data and isinstance(data["hands"], list):
            return len(data["hands"])

        if "hand_count" in data:
            return int(data["hand_count"])

        if "handCount" in data:
            return int(data["handCount"])

        return 0

    def _extract_player_count(self, data: dict[str, Any]) -> int:
        """플레이어 수 추출.

        Hands 배열의 Players에서 고유 플레이어 수 계산.

        다양한 형식 지원:
        - {"Hands": [{"Players": [...]}]}  # PascalCase
        - {"hands": [{"players": [...]}]}  # lowercase
        - {"player_count": 10}             # 직접 값
        """
        # 직접 값이 있으면 사용
        if "player_count" in data:
            return int(data["player_count"])

        if "playerCount" in data:
            return int(data["playerCount"])

        # Hands에서 추출
        hands = data.get("Hands") or data.get("hands") or []
        if not hands:
            return 0

        # 모든 핸드에서 고유 플레이어 수집
        all_players: set[str] = set()
        for hand in hands:
            if not isinstance(hand, dict):
                continue
            players = hand.get("Players") or hand.get("players") or []
            for player in players:
                # Name 또는 PlayerNum으로 고유 식별
                name = player.get("Name") or player.get("name")
                if name:
                    all_players.add(name)
                else:
                    # Name이 없으면 PlayerNum 사용
                    player_num = player.get("PlayerNum") or player.get("playerNum")
                    if player_num is not None:
                        all_players.add(f"player_{player_num}")

        return len(all_players)

    def _extract_payouts(self, data: dict[str, Any]) -> list[int] | None:
        """payouts 추출.

        다양한 형식 지원:
        - {"Payouts": [1000, 500, ...]}  # PascalCase (문서 기준)
        - {"payouts": [...]}
        """
        # PascalCase (문서 기준 - 02-GFX-JSON-DB.md)
        if "Payouts" in data and isinstance(data["Payouts"], list):
            return [int(p) for p in data["Payouts"]]

        if "payouts" in data and isinstance(data["payouts"], list):
            return [int(p) for p in data["payouts"]]

        return None

    @staticmethod
    def validate_json_structure(data: dict[str, Any]) -> list[str]:
        """JSON 구조 검증.

        Args:
            data: JSON 데이터

        Returns:
            오류 메시지 리스트 (빈 리스트면 유효)
        """
        errors = []

        # 필수 필드 확인 (유연한 검증 - PascalCase 포함)
        # 참고: 파일명에서 GameID 추출 가능하므로 ID 없어도 OK
        if not any(k in data for k in ["ID", "session_id", "session", "id"]):
            errors.append("session_id가 없습니다 (파일명에서 GameID 추출 시도)")

        return errors
