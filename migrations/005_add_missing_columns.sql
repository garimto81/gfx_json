-- ============================================================================
-- GFX Sync Agent - 누락된 컬럼 추가 마이그레이션
-- Purpose: gfx_sessions 테이블에 created_datetime_utc 컬럼 추가
-- Issue: PGRST204 - Could not find 'created_datetime_utc' column
-- Date: 2026-01-16
-- ============================================================================

-- ============================================================================
-- 1. created_datetime_utc 컬럼 추가
-- ============================================================================

-- 세션 생성 시간 컬럼 추가 (JSON의 CreatedDateTimeUTC 필드)
ALTER TABLE gfx_sessions
    ADD COLUMN IF NOT EXISTS created_datetime_utc TIMESTAMPTZ;

COMMENT ON COLUMN gfx_sessions.created_datetime_utc IS 'PokerGFX 세션 생성 시간 (원본 JSON의 CreatedDateTimeUTC)';

-- ============================================================================
-- 2. 기존 데이터 Backfill (created_at 값으로 초기화)
-- ============================================================================

UPDATE gfx_sessions
SET created_datetime_utc = created_at
WHERE created_datetime_utc IS NULL;

-- ============================================================================
-- 3. 인덱스 추가 (이미 있으면 무시)
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_gfx_sessions_created_datetime
    ON gfx_sessions(created_datetime_utc DESC);

-- ============================================================================
-- 완료 메시지
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE 'Migration 005: created_datetime_utc 컬럼 추가 완료';
END $$;
