-- ============================================================================
-- GFX Sync Agent - 긴급 호환성 마이그레이션
-- Version: 1.0.0
-- Date: 2026-01-15
-- Purpose: 코드와 실제 DB 스키마 정합성 확보
-- ============================================================================

-- ============================================================================
-- 문제 상황:
-- 1. 코드에서 gfx_pc_id, sync_source 사용 → 실제 DB에 없음
-- 2. 복합 UNIQUE 제약 (gfx_pc_id, file_hash) 부재
-- 3. 현재 UPSERT 실패 발생 가능
--
-- 해결 방안:
-- 1. gfx_pc_id, sync_source 컬럼 추가
-- 2. 기존 데이터 backfill (nas_path에서 추출)
-- 3. 복합 UNIQUE 제약 추가
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. 사전 검증 (중복 데이터 확인)
-- ============================================================================

-- 중복 session_id 확인
DO $$
DECLARE
    duplicate_count INT;
BEGIN
    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT session_id, COUNT(*) as cnt
        FROM gfx_sessions
        GROUP BY session_id
        HAVING COUNT(*) > 1
    ) duplicates;

    IF duplicate_count > 0 THEN
        RAISE WARNING '중복 session_id 발견: % 건. 수동 확인 필요.', duplicate_count;
    END IF;
END $$;

-- ============================================================================
-- 2. 컬럼 추가
-- ============================================================================

-- gfx_pc_id 컬럼 추가 (nullable로 시작)
ALTER TABLE gfx_sessions
    ADD COLUMN IF NOT EXISTS gfx_pc_id TEXT;

-- sync_source 컬럼 추가 (기본값: nas_central)
ALTER TABLE gfx_sessions
    ADD COLUMN IF NOT EXISTS sync_source TEXT DEFAULT 'nas_central';

COMMENT ON COLUMN gfx_sessions.gfx_pc_id IS 'GFX PC 식별자 (예: PC01, PC02)';
COMMENT ON COLUMN gfx_sessions.sync_source IS '동기화 소스 (nas_central, gfx_pc_direct)';

-- ============================================================================
-- 3. 기존 데이터 Backfill
-- ============================================================================

-- nas_path에서 PC ID 추출
-- 예: /nas/PC01/session_12345.json → PC01
UPDATE gfx_sessions
SET gfx_pc_id = CASE
    -- nas_path 패턴 매칭
    WHEN nas_path ~ '.*/(PC\d+)/.*' THEN
        (regexp_matches(nas_path, '.*/([^/]+)/[^/]+$'))[1]
    -- nas_path가 NULL이면 file_name에서 추출 시도
    WHEN file_name ~ '^(PC\d+)_.*' THEN
        (regexp_matches(file_name, '^([^_]+)_.*'))[1]
    -- 그 외에는 UNKNOWN
    ELSE 'UNKNOWN'
END
WHERE gfx_pc_id IS NULL;

-- 여전히 NULL인 경우 UNKNOWN으로 설정
UPDATE gfx_sessions
SET gfx_pc_id = 'UNKNOWN'
WHERE gfx_pc_id IS NULL;

-- ============================================================================
-- 4. NOT NULL 제약 추가
-- ============================================================================

ALTER TABLE gfx_sessions
    ALTER COLUMN gfx_pc_id SET NOT NULL;

-- ============================================================================
-- 5. 복합 UNIQUE 제약 추가
-- ============================================================================

-- 기존 file_hash UNIQUE 제약 제거
-- (session_id UNIQUE는 유지)
ALTER TABLE gfx_sessions
    DROP CONSTRAINT IF EXISTS gfx_sessions_file_hash_key;

-- 복합 UNIQUE 제약 추가 (gfx_pc_id, file_hash)
-- 같은 PC에서 같은 파일은 중복 불가
ALTER TABLE gfx_sessions
    ADD CONSTRAINT uq_gfx_sessions_pc_file
    UNIQUE (gfx_pc_id, file_hash);

COMMENT ON CONSTRAINT uq_gfx_sessions_pc_file ON gfx_sessions
    IS 'PC별 파일 해시 중복 방지 (같은 PC에서 같은 파일은 1번만)';

-- ============================================================================
-- 6. 인덱스 생성
-- ============================================================================

-- gfx_pc_id 인덱스 (조회 성능 향상)
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_pc_id
    ON gfx_sessions(gfx_pc_id);

-- sync_source 인덱스 (출처별 조회)
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_sync_source
    ON gfx_sessions(sync_source);

-- 복합 인덱스 (gfx_pc_id, created_at)
-- PC별 최신 세션 조회 최적화
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_pc_created
    ON gfx_sessions(gfx_pc_id, created_at DESC);

-- ============================================================================
-- 7. 데이터 검증
-- ============================================================================

DO $$
DECLARE
    total_count INT;
    null_pc_count INT;
    unknown_pc_count INT;
BEGIN
    -- 전체 레코드 수
    SELECT COUNT(*) INTO total_count FROM gfx_sessions;

    -- gfx_pc_id가 NULL인 레코드 수 (0이어야 함)
    SELECT COUNT(*) INTO null_pc_count
    FROM gfx_sessions
    WHERE gfx_pc_id IS NULL;

    -- gfx_pc_id가 UNKNOWN인 레코드 수
    SELECT COUNT(*) INTO unknown_pc_count
    FROM gfx_sessions
    WHERE gfx_pc_id = 'UNKNOWN';

    RAISE NOTICE '============================================';
    RAISE NOTICE 'Migration 004 - 데이터 검증 결과';
    RAISE NOTICE '============================================';
    RAISE NOTICE '전체 레코드: %', total_count;
    RAISE NOTICE 'NULL gfx_pc_id: % (0이어야 함)', null_pc_count;
    RAISE NOTICE 'UNKNOWN gfx_pc_id: % (수동 확인 권장)', unknown_pc_count;
    RAISE NOTICE '============================================';

    IF null_pc_count > 0 THEN
        RAISE EXCEPTION 'gfx_pc_id가 NULL인 레코드가 존재합니다. Migration 실패.';
    END IF;

    IF unknown_pc_count > 0 THEN
        RAISE WARNING 'UNKNOWN gfx_pc_id가 % 건 있습니다. 수동 확인이 필요합니다.', unknown_pc_count;
    END IF;
END $$;

-- ============================================================================
-- 8. PC별 통계 출력 (선택적)
-- ============================================================================

DO $$
DECLARE
    rec RECORD;
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE 'PC별 세션 통계';
    RAISE NOTICE '============================================';

    FOR rec IN
        SELECT
            gfx_pc_id,
            COUNT(*) as session_count,
            MIN(created_at) as first_session,
            MAX(created_at) as last_session
        FROM gfx_sessions
        GROUP BY gfx_pc_id
        ORDER BY session_count DESC
    LOOP
        RAISE NOTICE 'PC: %, 세션: %, 최초: %, 최근: %',
            rec.gfx_pc_id,
            rec.session_count,
            rec.first_session,
            rec.last_session;
    END LOOP;

    RAISE NOTICE '============================================';
END $$;

COMMIT;

-- ============================================================================
-- Rollback 스크립트 (실패 시 복구용)
-- ============================================================================

/*
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
*/

-- ============================================================================
-- 사용 예시 (Migration 적용 후 코드 동작 확인)
-- ============================================================================

/*
-- 1. INSERT 테스트 (gfx_pc_id 포함)
INSERT INTO gfx_sessions (
    session_id, gfx_pc_id, file_hash, file_name, raw_json
) VALUES (
    999999,
    'PC01',
    'test_hash_123',
    'test_session.json',
    '{}'::jsonb
);

-- 2. UPSERT 테스트 (on_conflict)
INSERT INTO gfx_sessions (
    session_id, gfx_pc_id, file_hash, file_name, raw_json
) VALUES (
    999999,
    'PC01',
    'test_hash_123',
    'test_session_updated.json',
    '{}'::jsonb
)
ON CONFLICT (gfx_pc_id, file_hash)
DO UPDATE SET
    file_name = EXCLUDED.file_name,
    updated_at = NOW();

-- 3. PC별 조회 테스트
SELECT gfx_pc_id, COUNT(*) as session_count
FROM gfx_sessions
GROUP BY gfx_pc_id
ORDER BY session_count DESC;

-- 4. 테스트 데이터 정리
DELETE FROM gfx_sessions WHERE session_id = 999999;
*/
