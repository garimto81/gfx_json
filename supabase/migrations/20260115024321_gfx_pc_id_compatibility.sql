-- ============================================================================
-- GFX Sync Agent - gfx_pc_id 호환성 마이그레이션
-- Purpose: 코드와 실제 DB 스키마 정합성 확보
-- ============================================================================

-- ============================================================================
-- 1. 컬럼 추가
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
-- 2. 기존 데이터 Backfill
-- ============================================================================

-- nas_path에서 PC ID 추출 (substring 사용)
UPDATE gfx_sessions
SET gfx_pc_id = CASE
    WHEN nas_path ~ '.*/PC\d+/.*' THEN
        substring(nas_path FROM '.*/([^/]+)/[^/]+$')
    WHEN file_name ~ '^PC\d+_.*' THEN
        substring(file_name FROM '^([^_]+)_.*')
    ELSE 'UNKNOWN'
END
WHERE gfx_pc_id IS NULL;

-- 여전히 NULL인 경우 UNKNOWN으로 설정
UPDATE gfx_sessions
SET gfx_pc_id = 'UNKNOWN'
WHERE gfx_pc_id IS NULL OR gfx_pc_id = '';

-- ============================================================================
-- 3. NOT NULL 제약 추가
-- ============================================================================

ALTER TABLE gfx_sessions
    ALTER COLUMN gfx_pc_id SET NOT NULL;

-- ============================================================================
-- 4. 복합 UNIQUE 제약 추가
-- ============================================================================

-- 기존 file_hash UNIQUE 제약 제거
ALTER TABLE gfx_sessions
    DROP CONSTRAINT IF EXISTS gfx_sessions_file_hash_key;

-- 복합 UNIQUE 제약 추가 (gfx_pc_id, file_hash)
ALTER TABLE gfx_sessions
    ADD CONSTRAINT uq_gfx_sessions_pc_file
    UNIQUE (gfx_pc_id, file_hash);

-- ============================================================================
-- 5. 인덱스 생성
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_gfx_sessions_pc_id
    ON gfx_sessions(gfx_pc_id);

CREATE INDEX IF NOT EXISTS idx_gfx_sessions_sync_source
    ON gfx_sessions(sync_source);

CREATE INDEX IF NOT EXISTS idx_gfx_sessions_pc_created
    ON gfx_sessions(gfx_pc_id, created_at DESC);
