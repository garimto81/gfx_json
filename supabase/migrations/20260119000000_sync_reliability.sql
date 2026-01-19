-- PRD-0007: GFX JSON Sync 신뢰성 개선
-- 문제: on_conflict=session_id 충돌 → file_hash 기반 중복 방지
--
-- 변경사항:
-- 1. file_hash UNIQUE 제약 추가 (멱등성 보장)
-- 2. gfx_pc_id 컬럼 추가 (PC 식별자 DB 저장)

-- 1. file_hash UNIQUE 제약 추가
-- 동일 파일 내용 중복 삽입 방지 (SHA-256 해시 기반)
DO $$
BEGIN
    -- 기존 UNIQUE 제약이 없는 경우에만 추가
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'gfx_sessions_file_hash_unique'
    ) THEN
        ALTER TABLE gfx_sessions
        ADD CONSTRAINT gfx_sessions_file_hash_unique UNIQUE (file_hash);

        RAISE NOTICE 'Added UNIQUE constraint on file_hash';
    ELSE
        RAISE NOTICE 'UNIQUE constraint on file_hash already exists';
    END IF;
END $$;

-- 2. gfx_pc_id 컬럼 추가 (없는 경우)
-- 데이터 출처 PC 식별자 저장
ALTER TABLE gfx_sessions
ADD COLUMN IF NOT EXISTS gfx_pc_id VARCHAR(50);

-- 3. gfx_pc_id 인덱스 추가 (PC별 조회 성능 향상)
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_pc_id ON gfx_sessions(gfx_pc_id);

-- 4. 기존 데이터의 gfx_pc_id 업데이트 (nas_path에서 추출 가능한 경우)
-- nas_path 형식: /nas/{gfx_pc_id}/{file_name}
UPDATE gfx_sessions
SET gfx_pc_id = split_part(nas_path, '/', 3)
WHERE gfx_pc_id IS NULL
  AND nas_path IS NOT NULL
  AND nas_path LIKE '/nas/%';

COMMENT ON CONSTRAINT gfx_sessions_file_hash_unique ON gfx_sessions IS
    'PRD-0007: file_hash 기반 중복 방지 - 동일 파일 내용 재삽입 방지';

COMMENT ON COLUMN gfx_sessions.gfx_pc_id IS
    'PRD-0007: GFX PC 식별자 (예: PC01, PC02) - 데이터 출처 추적용';
