# GFX Sync Agent - 스키마 마이그레이션 가이드

**Version**: 1.0.0
**Date**: 2026-01-15
**Related**: `docs/schema-analysis-report.md`

---

## Quick Start (긴급 조치)

### 1. 현재 상황

코드와 실제 Supabase DB 스키마가 불일치하여 **Sync Agent가 동작하지 않을 수 있습니다**.

**주요 문제**:
- 코드에서 `gfx_pc_id`, `sync_source` 사용 → 실제 DB에 없음
- UPSERT 시 `on_conflict="gfx_pc_id,file_hash"` 제약 조건 없음

### 2. 긴급 Migration 실행 (5분 소요)

```bash
# Staging 환경에서 먼저 테스트
supabase db push --db-url "postgresql://..."

# 또는 직접 SQL 실행
psql -h <host> -U postgres -d postgres -f migrations/004_emergency_compatibility.sql
```

### 3. 검증

```sql
-- 1. 컬럼 확인
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'gfx_sessions'
  AND column_name IN ('gfx_pc_id', 'sync_source')
ORDER BY column_name;

-- 기대 결과:
--  column_name  | data_type | is_nullable
-- --------------+-----------+-------------
--  gfx_pc_id    | text      | NO
--  sync_source  | text      | YES

-- 2. 제약 조건 확인
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'gfx_sessions'
  AND constraint_name = 'uq_gfx_sessions_pc_file';

-- 기대 결과:
--  constraint_name           | constraint_type
-- ---------------------------+-----------------
--  uq_gfx_sessions_pc_file   | UNIQUE

-- 3. 데이터 검증
SELECT
    gfx_pc_id,
    COUNT(*) as session_count,
    MIN(created_at) as first_session,
    MAX(created_at) as last_session
FROM gfx_sessions
GROUP BY gfx_pc_id
ORDER BY session_count DESC;
```

### 4. Sync Agent 재시작

```bash
# Docker Compose 사용 시
docker-compose restart sync-agent

# 직접 실행 시
python -m src.sync_agent.main_v3
```

---

## Phase별 로드맵

### Phase 1: 긴급 호환성 확보 (즉시)

**목표**: 현재 코드가 동작하도록 DB 스키마 수정

**작업**:
- [x] `gfx_pc_id`, `sync_source` 컬럼 추가
- [x] 복합 UNIQUE 제약 추가 (`gfx_pc_id, file_hash`)
- [x] 기존 데이터 backfill

**산출물**:
- `migrations/004_emergency_compatibility.sql`

**실행 방법**:
```bash
supabase db push
```

---

### Phase 2: Adapter 패턴 도입 (1-2주)

**목표**: DB 전용 필드 활용 시작 (`sync_status`, `nas_path`)

**작업**:
- [ ] `SupabaseSchemaAdapter` 적용
- [ ] `sync_status` 업데이트 로직 추가
- [ ] Dashboard에서 `sync_status` 표시
- [ ] 재시도 로직 구현 (`sync_status='failed'` 감지)

**코드 수정**:

#### 1. sync_service_v3.py 수정

```python
# BEFORE
async def _upsert_single(self, record: dict, path: str, gfx_pc_id: str):
    await self.supabase.upsert(
        table=self.settings.supabase_table,
        records=[record],
        on_conflict="gfx_pc_id,file_hash",
    )

# AFTER
from src.sync_agent.adapters import SupabaseSchemaAdapter

async def _upsert_single(self, record: dict, path: str, gfx_pc_id: str):
    # Adapter로 변환
    db_record = SupabaseSchemaAdapter.to_db_record(record, gfx_pc_id)

    try:
        await self.supabase.upsert(
            table=self.settings.supabase_table,
            records=[db_record],
            on_conflict="gfx_pc_id,file_hash",
        )

        # sync_status='success' 업데이트
        await self.supabase.update(
            table=self.settings.supabase_table,
            filters={"session_id": db_record["session_id"]},
            data=SupabaseSchemaAdapter.update_sync_status(
                db_record["session_id"], "success"
            ),
        )

        return SyncResult(success=True)

    except Exception as e:
        # sync_status='failed' 업데이트
        await self.supabase.update(
            table=self.settings.supabase_table,
            filters={"session_id": db_record["session_id"]},
            data=SupabaseSchemaAdapter.update_sync_status(
                db_record["session_id"], "failed", str(e)
            ),
        )
        raise
```

#### 2. Dashboard API 추가

```python
# src/dashboard/api/sync_status.py (신규)

from fastapi import APIRouter
from src.sync_agent.db.supabase_client import SupabaseClient

router = APIRouter(prefix="/api/sync", tags=["sync"])

@router.get("/status")
async def get_sync_status():
    """동기화 상태 통계 조회."""
    client = SupabaseClient(...)

    # sync_status별 카운트
    stats = await client.query(
        table="gfx_sessions",
        select="sync_status, COUNT(*) as count",
        group_by="sync_status",
    )

    return {
        "status": "ok",
        "data": stats,
    }

@router.get("/failed")
async def get_failed_sessions(limit: int = 50):
    """동기화 실패 세션 조회."""
    client = SupabaseClient(...)

    failed = await client.query(
        table="gfx_sessions",
        filters={"sync_status": "failed"},
        order_by="updated_at DESC",
        limit=limit,
    )

    return {
        "status": "ok",
        "data": failed,
    }
```

---

### Phase 3: 스키마 통합 (1-2개월)

**목표**: 로컬 Migration과 실제 DB 스키마 완전 일치

**작업**:
- [ ] `migrations/` 폴더 제거
- [ ] `supabase/migrations/` 단일화
- [ ] CI/CD에 `supabase db push` 통합
- [ ] 로컬 개발 환경 표준화 (`supabase start`)

**마일스톤**:

#### M1: Supabase CLI 기반 스키마 관리

```bash
# 실제 DB 스키마를 로컬로 가져오기
supabase db pull

# 로컬 변경사항 실제 DB로 푸시
supabase db push

# 로컬 개발 환경 시작 (Docker 기반)
supabase start
```

#### M2: CI/CD 통합

```yaml
# .github/workflows/schema-migration.yml

name: Schema Migration

on:
  push:
    branches: [main]
    paths:
      - 'supabase/migrations/**'

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Supabase CLI
        uses: supabase/setup-cli@v1

      # Staging 환경 먼저 적용
      - name: Push to Staging
        run: supabase db push --db-url ${{ secrets.STAGING_DB_URL }}

      # 검증 후 Production 적용
      - name: Verify Staging
        run: |
          # 검증 스크립트 실행
          python scripts/verify_schema.py

      - name: Push to Production
        if: success()
        run: supabase db push --db-url ${{ secrets.PROD_DB_URL }}
```

#### M3: 로컬 개발 가이드

```markdown
# 로컬 개발 환경 설정

## 1. Supabase CLI 설치

npm install -g supabase

## 2. 로컬 DB 시작

supabase start

# 출력 예시:
# API URL: http://localhost:54321
# DB URL: postgresql://postgres:postgres@localhost:54322/postgres
# Studio URL: http://localhost:54323

## 3. Migration 적용

supabase db reset  # 초기화 + Migration 자동 적용

## 4. Sync Agent 실행

# .env 파일 수정 (로컬 DB 사용)
SUPABASE_URL=http://localhost:54321
SUPABASE_SECRET_KEY=<로컬 service_role key>

python -m src.sync_agent.main_v3
```

---

## Rollback 절차

### Migration 실패 시

```sql
-- 1. 트랜잭션 롤백
ROLLBACK;

-- 2. 수동 Rollback (커밋 후 문제 발견 시)
BEGIN;

-- 복합 UNIQUE 제약 제거
ALTER TABLE gfx_sessions
    DROP CONSTRAINT IF EXISTS uq_gfx_sessions_pc_file;

-- 기존 file_hash UNIQUE 제약 복원
ALTER TABLE gfx_sessions
    ADD CONSTRAINT gfx_sessions_file_hash_key
    UNIQUE (file_hash);

-- 인덱스 제거
DROP INDEX IF EXISTS idx_gfx_sessions_pc_id;
DROP INDEX IF EXISTS idx_gfx_sessions_sync_source;
DROP INDEX IF EXISTS idx_gfx_sessions_pc_created;

-- 컬럼 제거
ALTER TABLE gfx_sessions DROP COLUMN IF EXISTS gfx_pc_id;
ALTER TABLE gfx_sessions DROP COLUMN IF EXISTS sync_source;

COMMIT;
```

### 데이터 복구

```sql
-- 백업에서 복원
TRUNCATE TABLE gfx_sessions;

COPY gfx_sessions FROM '/backup/gfx_sessions_20260115.csv' CSV HEADER;
```

---

## 테스트 체크리스트

### Migration 실행 전

- [ ] 실제 DB 백업 생성
  ```bash
  pg_dump -h <host> -U postgres -d postgres -t gfx_sessions > backup_20260115.sql
  ```
- [ ] 로컬 환경에서 Migration 테스트
  ```bash
  supabase start
  psql -h localhost -p 54322 -U postgres -f migrations/004_emergency_compatibility.sql
  ```
- [ ] 중복 데이터 확인
  ```sql
  SELECT gfx_pc_id, file_hash, COUNT(*)
  FROM gfx_sessions
  GROUP BY gfx_pc_id, file_hash
  HAVING COUNT(*) > 1;
  ```

### Migration 실행 중

- [ ] 트랜잭션 단위로 실행 (BEGIN/COMMIT)
- [ ] 각 단계별 RAISE NOTICE 확인
- [ ] 오류 발생 시 즉시 ROLLBACK

### Migration 완료 후

- [ ] 데이터 정합성 검증
  ```sql
  SELECT COUNT(*) FROM gfx_sessions WHERE gfx_pc_id IS NULL;  -- 0이어야 함
  ```
- [ ] Sync Agent 테스트 (샘플 파일 동기화)
  ```bash
  # 테스트 파일 생성
  echo '{"SessionID": 999999, "Hands": []}' > /nas/PC01/test_999999.json

  # 로그 확인 (UPSERT 성공 여부)
  docker logs sync-agent --tail 50
  ```
- [ ] Dashboard 동작 확인
  ```bash
  curl http://localhost:8000/api/sync/status
  ```

---

## FAQ

### Q1. Migration 중 다운타임이 있나요?

**A**: 긴급 Migration (004)는 **무중단**입니다.
- `ADD COLUMN` 연산은 metadata만 변경 (Lock 최소)
- `UPDATE` 연산은 배치로 처리 (대용량 테이블의 경우 시간 소요)

### Q2. 기존 데이터에 영향이 있나요?

**A**: 없습니다.
- `gfx_pc_id`는 `nas_path`에서 자동 추출
- 추출 실패 시 `UNKNOWN`으로 설정
- 모든 기존 데이터 보존

### Q3. UNKNOWN PC는 어떻게 처리하나요?

**A**: 수동 확인 후 업데이트
```sql
-- UNKNOWN PC 조회
SELECT id, file_name, nas_path
FROM gfx_sessions
WHERE gfx_pc_id = 'UNKNOWN';

-- 수동 업데이트
UPDATE gfx_sessions
SET gfx_pc_id = 'PC03'
WHERE id = '<uuid>';
```

### Q4. 복합 UNIQUE 제약 충돌은?

**A**: Migration 전 중복 제거
```sql
-- 중복 확인
SELECT gfx_pc_id, file_hash, COUNT(*)
FROM gfx_sessions
GROUP BY gfx_pc_id, file_hash
HAVING COUNT(*) > 1;

-- 중복 제거 (최신 것만 유지)
DELETE FROM gfx_sessions
WHERE id NOT IN (
    SELECT MAX(id)
    FROM gfx_sessions
    GROUP BY gfx_pc_id, file_hash
);
```

---

## 참조 문서

| 문서 | 설명 |
|------|------|
| `docs/schema-analysis-report.md` | 상세 분석 보고서 |
| `migrations/004_emergency_compatibility.sql` | 긴급 Migration SQL |
| `src/sync_agent/adapters/db_adapter.py` | Adapter 패턴 구현 |

---

**End of Guide**
