-- =============================================================================
-- FT-0011: NAS 중앙 통제 방식 Supabase 마이그레이션
-- 작성일: 2026-01-13
-- 설명: 여러 GFX PC를 중앙에서 관리하기 위한 테이블 구조 변경
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. gfx_sessions 테이블 수정: gfx_pc_id 컬럼 추가
-- -----------------------------------------------------------------------------

-- gfx_pc_id 컬럼 추가 (기존 데이터는 'UNKNOWN'으로 설정)
ALTER TABLE gfx_sessions
ADD COLUMN IF NOT EXISTS gfx_pc_id TEXT NOT NULL DEFAULT 'UNKNOWN';

-- 기존 file_hash UNIQUE 제약조건 제거
ALTER TABLE gfx_sessions
DROP CONSTRAINT IF EXISTS gfx_sessions_file_hash_key;

-- 새로운 UNIQUE 제약조건: PC별로 file_hash 고유
-- (동일 파일이 여러 PC에서 생성될 수 있으므로)
ALTER TABLE gfx_sessions
ADD CONSTRAINT gfx_sessions_pc_hash_unique UNIQUE (gfx_pc_id, file_hash);

-- gfx_pc_id 인덱스 (PC별 조회 성능)
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_pc_id
ON gfx_sessions(gfx_pc_id);

-- created_at 인덱스 (최신 데이터 조회)
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_created_at
ON gfx_sessions(created_at DESC);

-- sync_source 기본값 변경 (기존: 'gfx_pc_direct' → 'nas_central')
ALTER TABLE gfx_sessions
ALTER COLUMN sync_source SET DEFAULT 'nas_central';

-- -----------------------------------------------------------------------------
-- 2. sync_events 테이블 생성 (신규 - 대시보드용)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sync_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- PC 식별
    gfx_pc_id TEXT NOT NULL,

    -- 이벤트 유형: 'sync', 'error', 'offline', 'recovery', 'batch'
    event_type TEXT NOT NULL,

    -- 처리 건수
    file_count INTEGER DEFAULT 0,

    -- 오류 메시지 (event_type='error' 시)
    error_message TEXT,

    -- 추가 메타데이터 (JSON)
    metadata JSONB DEFAULT '{}',

    -- 생성 시간
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_sync_events_pc_id
ON sync_events(gfx_pc_id);

CREATE INDEX IF NOT EXISTS idx_sync_events_created_at
ON sync_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sync_events_type
ON sync_events(event_type);

-- 복합 인덱스 (PC + 시간 범위 쿼리 최적화)
CREATE INDEX IF NOT EXISTS idx_sync_events_pc_time
ON sync_events(gfx_pc_id, created_at DESC);

-- Realtime 활성화 (Next.js 대시보드용)
-- 주의: 이 명령은 Supabase 대시보드에서 수동 실행 필요할 수 있음
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime'
        AND tablename = 'sync_events'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE sync_events;
    END IF;
EXCEPTION
    WHEN undefined_object THEN
        -- publication이 없으면 무시
        NULL;
END $$;

-- -----------------------------------------------------------------------------
-- 3. pc_status 뷰 생성 (대시보드용 집계)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW pc_status AS
SELECT
    gfx_pc_id,

    -- 총 세션 수
    COUNT(*) AS total_sessions,

    -- 최근 1시간 세션 수
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') AS sessions_last_hour,

    -- 최근 24시간 세션 수
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') AS sessions_last_day,

    -- 마지막 동기화 시간
    MAX(created_at) AS last_sync_at,

    -- 상태 판정
    CASE
        WHEN MAX(created_at) > NOW() - INTERVAL '10 minutes' THEN 'online'
        WHEN MAX(created_at) > NOW() - INTERVAL '1 hour' THEN 'idle'
        ELSE 'offline'
    END AS status
FROM gfx_sessions
GROUP BY gfx_pc_id;

-- -----------------------------------------------------------------------------
-- 4. sync_stats 뷰 생성 (통계용)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW sync_stats AS
SELECT
    -- 전체 통계
    COUNT(*) AS total_synced,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') AS synced_last_hour,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') AS synced_last_day,
    COUNT(DISTINCT gfx_pc_id) AS active_pc_count,
    MAX(created_at) AS last_sync_at
FROM gfx_sessions;

-- -----------------------------------------------------------------------------
-- 5. error_summary 뷰 생성 (오류 집계)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW error_summary AS
SELECT
    gfx_pc_id,
    COUNT(*) AS error_count,
    MAX(created_at) AS last_error_at,
    array_agg(DISTINCT error_message) FILTER (WHERE error_message IS NOT NULL) AS error_types
FROM sync_events
WHERE event_type = 'error'
AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY gfx_pc_id;

-- -----------------------------------------------------------------------------
-- 6. RLS (Row Level Security) 정책 (선택사항)
-- -----------------------------------------------------------------------------

-- 현재는 service_role 키 사용으로 RLS 비활성화 상태
-- 추후 필요 시 활성화

-- ALTER TABLE sync_events ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow all for service role" ON sync_events
--   FOR ALL USING (auth.role() = 'service_role');

-- -----------------------------------------------------------------------------
-- 7. 함수: 오래된 sync_events 정리 (30일 이상)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION cleanup_old_sync_events()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM sync_events
    WHERE created_at < NOW() - INTERVAL '30 days';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- 8. 정리용 크론 작업 설정 (Supabase pg_cron 확장 필요)
-- -----------------------------------------------------------------------------

-- 매일 새벽 3시에 오래된 이벤트 정리
-- SELECT cron.schedule(
--     'cleanup-sync-events',
--     '0 3 * * *',
--     'SELECT cleanup_old_sync_events()'
-- );

-- =============================================================================
-- 마이그레이션 완료
-- =============================================================================

-- 검증 쿼리
-- SELECT * FROM pc_status;
-- SELECT * FROM sync_stats;
-- SELECT * FROM error_summary;
