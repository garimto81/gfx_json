"""NAS -> Supabase 업로드 테스트 스크립트.

사용법:
    # 로컬 테스트 (Supabase Mock)
    python scripts/test_nas_upload.py --mock

    # 실제 Supabase 연결 테스트
    python scripts/test_nas_upload.py --live

    # 특정 PC 테스트
    python scripts/test_nas_upload.py --pc PC01 --mock

기능:
    1. NAS JSON 파일 파싱
    2. Supabase 스키마로 변환
    3. DB 업로드 (또는 Mock)
    4. 결과 검증
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

# Windows 콘솔 UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 프로젝트 루트를 PYTHONPATH에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.sync_agent.core.json_parser import JsonParser


@dataclass
class UploadResult:
    """업로드 결과."""

    file_path: str
    success: bool
    session_id: int | None = None
    record_id: str | None = None
    error: str | None = None
    duration_ms: int = 0


class MockSupabaseClient:
    """테스트용 Mock Supabase 클라이언트."""

    def __init__(self):
        self.records: dict[str, list[dict]] = {"gfx_sessions": []}
        self.is_connected = True

    async def upsert(
        self,
        table: str,
        records: list[dict],
        on_conflict: str = "session_id",
    ) -> dict[str, Any]:
        """Mock upsert."""
        results = []
        for record in records:
            # 중복 체크
            existing = None
            for i, existing_record in enumerate(self.records[table]):
                if existing_record.get(on_conflict) == record.get(on_conflict):
                    existing = i
                    break

            record_id = str(uuid4())
            record["id"] = record_id
            record["created_at"] = datetime.utcnow().isoformat()
            record["updated_at"] = datetime.utcnow().isoformat()

            if existing is not None:
                self.records[table][existing] = record
            else:
                self.records[table].append(record)

            results.append({"id": record_id})

        return {"data": results}

    async def select(
        self,
        table: str,
        columns: str = "*",
        filters: dict | None = None,
    ) -> list[dict]:
        """Mock select."""
        records = self.records.get(table, [])
        if filters:
            for key, value in filters.items():
                records = [r for r in records if r.get(key) == value]
        return records

    def get_record_count(self, table: str) -> int:
        """레코드 수 반환."""
        return len(self.records.get(table, []))


class NASUploadTester:
    """NAS 업로드 테스터."""

    def __init__(
        self,
        use_mock: bool = True,
        target_pc: str | None = None,
    ):
        self.parser = JsonParser()
        self.use_mock = use_mock
        self.target_pc = target_pc

        if use_mock:
            self.client = MockSupabaseClient()
        else:
            # 실제 Supabase 클라이언트는 환경 변수 필요
            self._init_live_client()

    def _init_live_client(self):
        """실제 Supabase 클라이언트 초기화."""
        from dotenv import load_dotenv

        from src.sync_agent.db.supabase_client import SupabaseClient

        # .env 파일 로드
        load_dotenv(project_root / ".env")

        # 여러 환경 변수 형식 지원
        supabase_url = os.getenv("GFX_SYNC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
        supabase_key = (
            os.getenv("GFX_SYNC_SUPABASE_SECRET_KEY")
            or os.getenv("SUPABASE_SECRET_KEY")
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )

        if not supabase_url or not supabase_key:
            raise ValueError(
                "환경 변수 필요:\n"
                "  - SUPABASE_URL 또는 GFX_SYNC_SUPABASE_URL\n"
                "  - SUPABASE_SECRET_KEY 또는 GFX_SYNC_SUPABASE_SECRET_KEY\n"
                "또는 --mock 옵션으로 테스트하세요."
            )

        print(f"Supabase URL: {supabase_url}")
        print(f"Supabase Key: {supabase_key[:15]}...{supabase_key[-4:]}")

        self.client = SupabaseClient(url=supabase_url, secret_key=supabase_key)

    def discover_json_files(self) -> list[tuple[str, str]]:
        """JSON 파일 탐색. (파일경로, PC ID) 튜플 반환."""
        test_dirs = [
            project_root / "test_nas_data",
            project_root / "test_data",
        ]

        files = []
        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            for json_file in test_dir.rglob("*.json"):
                # PC ID 추출
                parts = json_file.relative_to(test_dir).parts
                gfx_pc_id = parts[0] if parts else "UNKNOWN"

                # 타겟 PC 필터링
                if self.target_pc and gfx_pc_id != self.target_pc:
                    continue

                files.append((str(json_file), gfx_pc_id))

        return files

    async def upload_file(
        self,
        file_path: str,
        gfx_pc_id: str,
    ) -> UploadResult:
        """단일 파일 업로드."""
        start_time = datetime.now()

        # 1. JSON 파싱
        parse_result = self.parser.parse(file_path, gfx_pc_id)
        if not parse_result.success:
            return UploadResult(
                file_path=file_path,
                success=False,
                error=f"파싱 실패: {parse_result.error}",
            )

        record = parse_result.record

        # 2. DB 스키마에 맞게 변환
        db_record = {
            "gfx_pc_id": record["gfx_pc_id"],
            "file_hash": record["file_hash"],
            "file_name": record["file_name"],
            "session_id": record["session_id"],
            "raw_json": record["raw_json"],
            "sync_source": record.get("sync_source", "nas_central"),
        }

        # Optional 필드
        if record.get("table_type"):
            db_record["table_type"] = record["table_type"]
        if record.get("event_title"):
            db_record["event_title"] = record["event_title"]
        if record.get("software_version"):
            db_record["software_version"] = record["software_version"]
        if record.get("hand_count"):
            db_record["hand_count"] = record["hand_count"]
        if record.get("created_datetime_utc"):
            db_record["created_datetime_utc"] = record["created_datetime_utc"]

        # NAS 경로 추가
        db_record["nas_path"] = f"/nas/{gfx_pc_id}/{Path(file_path).name}"

        # 3. DB 업로드
        try:
            result = await self.client.upsert(
                table="gfx_sessions",
                records=[db_record],
                on_conflict="gfx_pc_id,file_hash",  # 복합 키
            )

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # Mock과 Live의 결과 형식 통일 처리
            if isinstance(result, dict):
                # Mock 결과 형식
                record_id = result["data"][0]["id"] if result.get("data") else None
                success = True
            else:
                # Live 결과 형식 (UpsertResult)
                success = result.success
                record_id = None

            return UploadResult(
                file_path=file_path,
                success=success,
                session_id=record["session_id"],
                record_id=record_id,
                duration_ms=duration_ms,
            )

        except Exception as e:
            return UploadResult(
                file_path=file_path,
                success=False,
                session_id=record["session_id"],
                error=str(e),
            )

    async def run_test(self) -> list[UploadResult]:
        """전체 테스트 실행."""
        files = self.discover_json_files()
        print(f"\n📂 발견된 JSON 파일: {len(files)}개")

        if not files:
            print("⚠️  테스트할 파일이 없습니다.")
            return []

        # Live 클라이언트 연결
        if not self.use_mock:
            print("\n🔌 Supabase 연결 중...")
            await self.client.connect()

            # 헬스체크
            is_healthy = await self.client.health_check()
            if is_healthy:
                print("✅ Supabase 연결 성공!")
            else:
                print("⚠️  Supabase 헬스체크 실패 (연결은 시도)")

        results = []
        try:
            for file_path, gfx_pc_id in files:
                print(f"\n처리 중: {Path(file_path).name} (PC: {gfx_pc_id})")
                result = await self.upload_file(file_path, gfx_pc_id)

                if result.success:
                    print(
                        f"  ✅ 성공: session_id={result.session_id} ({result.duration_ms}ms)"
                    )
                else:
                    print(f"  ❌ 실패: {result.error}")

                results.append(result)
        finally:
            # Live 클라이언트 연결 해제
            if not self.use_mock:
                await self.client.close()
                print("\n🔌 Supabase 연결 종료")

        return results

    async def verify_results(self, results: list[UploadResult]):
        """업로드 결과 검증."""
        print("\n" + "=" * 60)
        print("📊 업로드 결과 검증")
        print("=" * 60)

        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count

        print(f"\n업로드 결과: {success_count}/{len(results)} 성공")

        if self.use_mock:
            # Mock DB 검증
            record_count = self.client.get_record_count("gfx_sessions")
            print(f"Mock DB 레코드 수: {record_count}")

            # 샘플 레코드 출력
            records = await self.client.select("gfx_sessions")
            if records:
                print("\n샘플 레코드:")
                for record in records[:3]:
                    print(f"  - session_id: {record.get('session_id')}")
                    print(f"    gfx_pc_id: {record.get('gfx_pc_id')}")
                    print(f"    table_type: {record.get('table_type')}")
                    print(
                        f"    created_datetime_utc: {record.get('created_datetime_utc')}"
                    )
                    print()
        else:
            # Live DB에서 검증
            print("\n🔍 Supabase에서 업로드된 데이터 확인 중...")
            await self.client.connect()
            try:
                # 업로드한 session_id로 조회
                uploaded_ids = [
                    r.session_id for r in results if r.success and r.session_id
                ]
                if uploaded_ids:
                    # 최근 업로드된 데이터 조회
                    records = await self.client.select(
                        "gfx_sessions",
                        columns="session_id,gfx_pc_id,table_type,event_title,created_datetime_utc,hand_count",
                        limit=5,
                    )
                    if records:
                        print(f"\n✅ Supabase에서 {len(records)}개 레코드 조회됨:")
                        for record in records:
                            print(f"  - session_id: {record.get('session_id')}")
                            print(f"    gfx_pc_id: {record.get('gfx_pc_id')}")
                            print(f"    table_type: {record.get('table_type')}")
                            print(f"    event_title: {record.get('event_title')}")
                            print(
                                f"    created_datetime_utc: {record.get('created_datetime_utc')}"
                            )
                            print(f"    hand_count: {record.get('hand_count')}")
                            print()
            finally:
                await self.client.close()

        # 실패 항목 출력
        if fail_count > 0:
            print("\n실패 항목:")
            for result in results:
                if not result.success:
                    print(f"  - {Path(result.file_path).name}: {result.error}")


def main():
    """메인 실행."""
    parser = argparse.ArgumentParser(description="NAS → Supabase 업로드 테스트")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Mock Supabase 사용 (기본값)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="실제 Supabase 연결",
    )
    parser.add_argument(
        "--pc",
        type=str,
        help="특정 PC만 테스트 (예: PC01)",
    )

    args = parser.parse_args()

    # 기본값은 mock
    use_mock = not args.live

    print("=" * 60)
    print("🧪 NAS → Supabase 업로드 테스트")
    print("=" * 60)
    print(f"모드: {'Mock' if use_mock else 'Live'}")
    if args.pc:
        print(f"타겟 PC: {args.pc}")

    try:
        tester = NASUploadTester(
            use_mock=use_mock,
            target_pc=args.pc,
        )

        # 비동기 실행
        results = asyncio.run(tester.run_test())
        asyncio.run(tester.verify_results(results))

        # 종료 코드
        fail_count = sum(1 for r in results if not r.success)
        if fail_count > 0:
            print(f"\n❌ {fail_count}개 파일 업로드 실패")
            return 1

        print("\n✅ 모든 테스트 통과!")
        return 0

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
