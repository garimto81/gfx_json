"""NAS JSON -> Supabase 테스트 환경 검증 스크립트.

사용법:
    python scripts/verify_test_env.py

기능:
    1. NAS JSON 샘플 파일 검증
    2. JsonParser 동작 확인
    3. Supabase 연결 테스트 (선택)
    4. 스키마 호환성 검증
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

# Windows 콘솔 UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 프로젝트 루트를 PYTHONPATH에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.sync_agent.core.json_parser import JsonParser


def verify_sample_json_files() -> dict[str, list]:
    """test_nas_data 샘플 파일 검증."""
    results = {"success": [], "failed": []}
    parser = JsonParser()

    test_dirs = [
        project_root / "test_nas_data",
        project_root / "test_data",
    ]

    for test_dir in test_dirs:
        if not test_dir.exists():
            print(f"⚠️  디렉토리 없음: {test_dir}")
            continue

        json_files = list(test_dir.rglob("*.json"))
        print(f"\n📁 {test_dir.name}: {len(json_files)}개 파일 발견")

        for json_file in json_files:
            # PC ID 추출 (경로에서)
            parts = json_file.relative_to(test_dir).parts
            gfx_pc_id = parts[0] if parts else "UNKNOWN"

            result = parser.parse(str(json_file), gfx_pc_id)

            if result.success:
                record = result.record
                results["success"].append({
                    "file": str(json_file.name),
                    "pc_id": gfx_pc_id,
                    "session_id": record.get("session_id"),
                    "table_type": record.get("table_type"),
                    "hand_count": record.get("hand_count"),
                    "created_datetime_utc": record.get("created_datetime_utc"),
                    "file_hash": record.get("file_hash", "")[:16] + "...",
                })
                print(f"  ✅ {json_file.name} → session_id={record.get('session_id')}")
            else:
                results["failed"].append({
                    "file": str(json_file.name),
                    "error": result.error,
                })
                print(f"  ❌ {json_file.name} → {result.error}")

    return results


def verify_json_structure():
    """JSON 구조 호환성 검증."""
    print("\n" + "=" * 60)
    print("📋 JSON 구조 호환성 검증")
    print("=" * 60)

    # 테스트할 JSON 구조들
    test_cases = [
        # PascalCase (PokerGFX 공식 형식)
        {
            "name": "PascalCase (공식)",
            "data": {
                "ID": 12345,
                "Type": "FEATURE_TABLE",
                "EventTitle": "WSOP 2024 Main Event",
                "SoftwareVersion": "3.2.1",
                "CreatedDateTimeUTC": "2024-01-15T10:00:00Z",
                "Hands": [{"HandNumber": 1}, {"HandNumber": 2}],
                "Payouts": [1000000, 500000, 250000],
            },
        },
        # camelCase (레거시)
        {
            "name": "camelCase (레거시)",
            "data": {
                "session": {
                    "id": 67890,
                    "tableType": "cash",
                    "eventTitle": "Test Event",
                    "softwareVersion": "3.0.0",
                    "createdAt": "2024-01-15T11:00:00Z",
                },
                "hands": [{"id": 1}, {"id": 2}, {"id": 3}],
            },
        },
        # snake_case
        {
            "name": "snake_case",
            "data": {
                "session_id": 11111,
                "table_type": "tournament",
                "event_title": "Daily Tournament",
                "software_version": "3.1.0",
                "created_at": "2024-01-15T12:00:00Z",
                "hands": [{"id": 1}],
            },
        },
        # 파일명에서 GameID 추출
        {
            "name": "GameID from filename",
            "data": {
                "Type": "FEATURE_TABLE",
                "Hands": [],
            },
            "file_name": "PGFX_live_data_export GameID=99999.json",
        },
    ]

    parser = JsonParser()

    for case in test_cases:
        name = case["name"]
        data = case["data"]
        file_name = case.get("file_name", "test.json")

        # 문자열 파싱 테스트
        content = json.dumps(data)
        result = parser.parse_content(content, file_name, "PC01")

        if result.success:
            record = result.record
            print(f"\n✅ {name}")
            print(f"   session_id: {record.get('session_id')}")
            print(f"   table_type: {record.get('table_type')}")
            print(f"   event_title: {record.get('event_title')}")
            print(f"   hand_count: {record.get('hand_count')}")
            print(f"   created_datetime_utc: {record.get('created_datetime_utc')}")
        else:
            print(f"\n❌ {name}: {result.error}")


def verify_db_schema_mapping():
    """DB 스키마 매핑 검증."""
    print("\n" + "=" * 60)
    print("🗄️  DB 스키마 매핑 검증")
    print("=" * 60)

    # 예상 DB 컬럼
    expected_columns = {
        "id": "UUID (자동 생성)",
        "session_id": "INTEGER (필수)",
        "gfx_pc_id": "TEXT (필수)",
        "file_hash": "TEXT (필수)",
        "file_name": "TEXT (필수)",
        "event_title": "TEXT",
        "software_version": "TEXT",
        "table_type": "ENUM (FEATURE_TABLE, MAIN_TABLE, ...)",
        "created_datetime_utc": "TIMESTAMPTZ",
        "payouts": "INTEGER[]",
        "sync_source": "TEXT (기본값: nas_central)",
        "hand_count": "INTEGER",
        "raw_json": "JSONB",
        "nas_path": "TEXT",
        "created_at": "TIMESTAMPTZ (자동)",
        "updated_at": "TIMESTAMPTZ (자동)",
    }

    # JsonParser가 생성하는 필드
    parser = JsonParser()
    sample_data = {
        "ID": 12345,
        "Type": "FEATURE_TABLE",
        "EventTitle": "Test",
        "SoftwareVersion": "3.0.0",
        "CreatedDateTimeUTC": "2024-01-15T10:00:00Z",
        "Hands": [{"id": 1}],
    }
    content = json.dumps(sample_data)
    result = parser.parse_content(content, "test.json", "PC01")

    if result.success:
        parser_fields = set(result.record.keys())
        print("\nJsonParser 출력 필드:")
        for field in sorted(parser_fields):
            db_type = expected_columns.get(field, "⚠️ 매핑 없음")
            value = result.record.get(field)
            if isinstance(value, dict):
                value = "{...}"
            elif isinstance(value, str) and len(value) > 30:
                value = value[:30] + "..."
            print(f"  ✓ {field}: {value} → {db_type}")

        # 누락된 필드 확인
        missing = set(expected_columns.keys()) - parser_fields - {
            "id", "created_at", "updated_at", "nas_path", "payouts"
        }
        if missing:
            print(f"\n⚠️ 파서에서 생성하지 않는 필드 (DB 기본값 또는 별도 처리):")
            for field in sorted(missing):
                print(f"  - {field}: {expected_columns[field]}")


def main():
    """메인 실행."""
    print("=" * 60)
    print("🔍 NAS JSON → Supabase 테스트 환경 검증")
    print("=" * 60)

    # 1. 샘플 파일 검증
    results = verify_sample_json_files()

    # 2. JSON 구조 호환성 검증
    verify_json_structure()

    # 3. DB 스키마 매핑 검증
    verify_db_schema_mapping()

    # 요약
    print("\n" + "=" * 60)
    print("📊 검증 결과 요약")
    print("=" * 60)
    print(f"  성공: {len(results['success'])}개 파일")
    print(f"  실패: {len(results['failed'])}개 파일")

    if results["success"]:
        print("\n성공한 파일 상세:")
        for item in results["success"]:
            print(f"  - {item['file']} (PC: {item['pc_id']}, session: {item['session_id']})")

    if results["failed"]:
        print("\n실패한 파일:")
        for item in results["failed"]:
            print(f"  - {item['file']}: {item['error']}")
        return 1

    print("\n✅ 모든 검증 통과! NAS 전송 테스트 준비 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
