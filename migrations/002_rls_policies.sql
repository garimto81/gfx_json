-- ============================================================================
-- RLS (Row Level Security) 정책
-- Supabase 환경용
-- ============================================================================

-- ============================================================================
-- RLS 활성화
-- ============================================================================
ALTER TABLE gfx_players ENABLE ROW LEVEL SECURITY;
ALTER TABLE gfx_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gfx_hands ENABLE ROW LEVEL SECURITY;
ALTER TABLE gfx_hand_players ENABLE ROW LEVEL SECURITY;
ALTER TABLE gfx_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_log ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- gfx_players 정책
-- ============================================================================
DROP POLICY IF EXISTS "gfx_players_select_authenticated" ON gfx_players;
CREATE POLICY "gfx_players_select_authenticated"
    ON gfx_players FOR SELECT
    USING (auth.role() = 'authenticated');

DROP POLICY IF EXISTS "gfx_players_all_service" ON gfx_players;
CREATE POLICY "gfx_players_all_service"
    ON gfx_players FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================================
-- gfx_sessions 정책
-- ============================================================================
DROP POLICY IF EXISTS "gfx_sessions_select_authenticated" ON gfx_sessions;
CREATE POLICY "gfx_sessions_select_authenticated"
    ON gfx_sessions FOR SELECT
    USING (auth.role() = 'authenticated');

DROP POLICY IF EXISTS "gfx_sessions_all_service" ON gfx_sessions;
CREATE POLICY "gfx_sessions_all_service"
    ON gfx_sessions FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================================
-- gfx_hands 정책
-- ============================================================================
DROP POLICY IF EXISTS "gfx_hands_select_authenticated" ON gfx_hands;
CREATE POLICY "gfx_hands_select_authenticated"
    ON gfx_hands FOR SELECT
    USING (auth.role() = 'authenticated');

DROP POLICY IF EXISTS "gfx_hands_all_service" ON gfx_hands;
CREATE POLICY "gfx_hands_all_service"
    ON gfx_hands FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================================
-- gfx_hand_players 정책
-- ============================================================================
DROP POLICY IF EXISTS "gfx_hand_players_select_authenticated" ON gfx_hand_players;
CREATE POLICY "gfx_hand_players_select_authenticated"
    ON gfx_hand_players FOR SELECT
    USING (auth.role() = 'authenticated');

DROP POLICY IF EXISTS "gfx_hand_players_all_service" ON gfx_hand_players;
CREATE POLICY "gfx_hand_players_all_service"
    ON gfx_hand_players FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================================
-- gfx_events 정책
-- ============================================================================
DROP POLICY IF EXISTS "gfx_events_select_authenticated" ON gfx_events;
CREATE POLICY "gfx_events_select_authenticated"
    ON gfx_events FOR SELECT
    USING (auth.role() = 'authenticated');

DROP POLICY IF EXISTS "gfx_events_all_service" ON gfx_events;
CREATE POLICY "gfx_events_all_service"
    ON gfx_events FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================================
-- sync_log 정책
-- ============================================================================
DROP POLICY IF EXISTS "sync_log_select_authenticated" ON sync_log;
CREATE POLICY "sync_log_select_authenticated"
    ON sync_log FOR SELECT
    USING (auth.role() = 'authenticated');

DROP POLICY IF EXISTS "sync_log_all_service" ON sync_log;
CREATE POLICY "sync_log_all_service"
    ON sync_log FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================================
-- 완료 메시지
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE 'RLS 정책 적용 완료';
END $$;
