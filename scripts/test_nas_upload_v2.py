"""NAS -> Supabase 업로드 테스트 스크립트 v2.

현재 실제 DB 스키마에 맞춘 버전.
(gfx_pc_id, created_datetime_utc, sync_source 컬럼 없음)

사용법:
    python scripts/test_nas_upload_v2.py --live
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

# Windows 콘솔 UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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
    error: str | None = None
    duration_ms: int = 0


class NASUploadTester:
    """NAS 업로드 테스터 (현재 스키마용)."""

    def __init__(self, target_pc: str | None = None):
        self.parser = JsonParser()
        self.target_pc = target_pc
        self._init_client()

    def _init_client(self):
        """Supabase 클라이언트 초기화."""
        from dotenv import load_dotenv
        from src.sync_agent.db.supabase_client import SupabaseClient

        # .env 파일 로드
        load_dotenv(project_root / ".env")

        # 여러 환경 변수 형식 지원
        supabase_url = os.getenv("GFX_SYNC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
        supabase_key = (
            os.getenv("GFX_SYNC_SUPABASE_SECRET_KEY")
            or os.getenv("SUPABASE_SECRET_KEY")
        )

        if not supabase_url or not supabase_key:
            raise ValueError("환경 변수 필요: SUPABASE_URL, SUPABASE_SECRET_KEY")

        print(f"Supabase URL: {supabase_url}")
        print(f"Supabase Key: {supabase_key[:15]}...{supabase_key[-4:]}")

        self.client = SupabaseClient(url=supabase_url, secret_key=supabase_key)

    def discover_json_files(self) -> list[tuple[str, str]]:
        """JSON 파일 탐색. 세션 파일만 (pc_registry 제외)."""
        test_dirs = [
            project_root / "test_nas_data",
            project_root / "test_data",
        ]

        files = []
        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            for json_file in test_dir.rglob("*.json"):
                # pc_registry.json 제외
                if "registry" in json_file.name.lower():
                    continue

                # PC ID 추출
                parts = json_file.relative_to(test_dir).parts
                gfx_pc_id = parts[0] if parts else "UNKNOWN"

                # 타겟 PC 필터링
                if self.target_pc and gfx_pc_id != self.target_pc:
                    continue

                files.append((str(json_file), gfx_pc_id))

        return files

    async def upload_file(self, file_path: str, gfx_pc_id: str) -> UploadResult:
        """단일 파일 업로드 (현재 스키마에 맞춤)."""
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
        session_id = record.get("session_id")

        if not session_id:
            return UploadResult(
                file_path=file_path,
                success=False,
                error="session_id 없음",
            )

        # 2. 현재 DB 스키마에 맞는 레코드 생성
        # 현재 스키마: session_id, file_name, file_hash, nas_path, table_type,
        #             event_title, software_version, payouts, hand_count, raw_json 등
        db_record = {
            "session_id": session_id,
            "file_name": record["file_name"],
            "file_hash": record["file_hash"],
            "raw_json": record["raw_json"],
        }

        # Optional 필드 (현재 스키마에 있는 것만)
        if record.get("table_type"):
            db_record["table_type"] = record["table_type"]
        if record.get("event_title"):
            db_record["event_title"] = record["event_title"]
        if record.get("software_version"):
            db_record["software_version"] = record["software_version"]
        if record.get("hand_count"):
            db_record["hand_count"] = record["hand_count"]

        # NAS 경로 추가
        db_record["nas_path"] = f"/nas/{gfx_pc_id}/{Path(file_path).name}"

        # 3. DB 업로드
        try:
            result = await self.client.upsert(
                table="gfx_sessions",
                records=[db_record],
                on_conflict="session_id",  # 현재 스키마는 session_id만 UNIQUE
            )

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            return UploadResult(
                file_path=file_path,
                success=result.success,
                session_id=session_id,
                error=result.error if not result.success else None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            return UploadResult(
                file_path=file_path,
                success=False,
                session_id=session_id,
                error=str(e),
            )

    async def run_test(self) -> list[UploadResult]:
        """전체 테스트 실행."""
        files = self.discover_json_files()
        print(f"\n📂 발견된 JSON 파일: {len(files)}개 (pc_registry 제외)")

        if not files:
            print("⚠️  테스트할 파일이 없습니다.")
            return []

        print("\n🔌 Supabase 연결 중...")
        await self.client.connect()

        is_healthy = await self.client.health_check()
        if is_healthy:
            print("✅ Supabase 연결 성공!")
        else:
            print("⚠️  Supabase 헬스체크 실패")

        results = []
        try:
            for file_path, gfx_pc_id in files:
                print(f"\n처리 중: {Path(file_path).name} (PC: {gfx_pc_id})")
                result = await self.upload_file(file_path, gfx_pc_id)

                if result.success:
                    print(f"  ✅ 성공: session_id={result.session_id} ({result.duration_ms}ms)")
                else:
                    print(f"  ❌ 실패: {result.error}")

                results.append(result)
        finally:
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

        # Live DB에서 검증
        print("\n🔍 Supabase에서 업로드된 데이터 확인 중...")
        await self.client.connect()
        try:
            records = await self.client.select(
                "gfx_sessions",
                columns="session_id,file_name,table_type,event_title,hand_count,nas_path",
                limit=10,
            )
            if records:
                print(f"\n✅ Supabase에서 {len(records)}개 레코드 조회됨:")
                for record in records:
                    print(f"  - session_id: {record.get('session_id')}")
                    print(f"    file_name: {record.get('file_name')}")
                    print(f"    table_type: {record.get('table_type')}")
                    print(f"    event_title: {record.get('event_title')}")
                    print(f"    hand_count: {record.get('hand_count')}")
                    print(f"    nas_path: {record.get('nas_path')}")
                    print()
        finally:
            await self.client.close()

        if fail_count > 0:
            print("\n실패 항목:")
            for result in results:
                if not result.success:
                    print(f"  - {Path(result.file_path).name}: {result.error}")


def main():
    """메인 실행."""
    parser = argparse.ArgumentParser(description="NAS -> Supabase 업로드 테스트 v2")
    parser.add_argument("--pc", type=str, help="특정 PC만 테스트 (예: PC01)")
    parser.add_argument("--live", action="store_true", help="Live 테스트 (기본)")

    args = parser.parse_args()

    print("=" * 60)
    print("🧪 NAS -> Supabase 업로드 테스트 v2")
    print("   (현재 DB 스키마에 맞춤)")
    print("=" * 60)

    try:
        tester = NASUploadTester(target_pc=args.pc)
        results = asyncio.run(tester.run_test())
        asyncio.run(tester.verify_results(results))

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
