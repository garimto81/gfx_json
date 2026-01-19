-- ============================================================================
-- GFX JSON 정규화 테이블 마이그레이션
-- Version: 2.0.0
-- Date: 2026-01-16
-- Project: PokerGFX JSON to Supabase Normalization
-- SSOT: C:\claude\automation_schema\docs\02-GFX-JSON-DB.md
-- ============================================================================

-- ============================================================================
-- ENUM Types (PRD Section 3)
-- ============================================================================

-- 테이블 타입 (게임 종류)
DO $$ BEGIN
    CREATE TYPE table_type AS ENUM (
        'FEATURE_TABLE',
        'MAIN_TABLE',
        'FINAL_TABLE',
        'SIDE_TABLE',
        'UNKNOWN'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 게임 변형
DO $$ BEGIN
    CREATE TYPE game_variant AS ENUM (
        'HOLDEM',
        'OMAHA',
        'OMAHA_HILO',
        'STUD',
        'STUD_HILO',
        'RAZZ',
        'DRAW',
        'MIXED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 게임 클래스
DO $$ BEGIN
    CREATE TYPE game_class AS ENUM (
        'FLOP',
        'STUD',
        'DRAW',
        'MIXED'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 베팅 구조
DO $$ BEGIN
    CREATE TYPE bet_structure AS ENUM (
        'NOLIMIT',
        'POTLIMIT',
        'LIMIT',
        'SPREAD_LIMIT'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 이벤트 타입 (액션)
DO $$ BEGIN
    CREATE TYPE event_type AS ENUM (
        'FOLD',
        'CHECK',
        'CALL',
        'BET',
        'RAISE',
        'ALL_IN',
        'BOARD_CARD',
        'ANTE',
        'BLIND',
        'STRADDLE',
        'BRING_IN',
        'MUCK',
        'SHOW',
        'WIN'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 동기화 상태
DO $$ BEGIN
    CREATE TYPE sync_status AS ENUM (
        'pending',
        'synced',
        'updated',
        'failed',
        'archived'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- 1. gfx_players (플레이어 마스터)
-- ============================================================================
CREATE TABLE IF NOT EXISTS gfx_players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 플레이어 식별 (name + long_name 해시로 중복 방지)
    player_hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    long_name TEXT DEFAULT '',

    -- 누적 통계
    total_hands_played INTEGER DEFAULT 0,
    total_sessions INTEGER DEFAULT 0,

    -- 타임스탬프
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_gfx_players_hash ON gfx_players(player_hash);
CREATE INDEX IF NOT EXISTS idx_gfx_players_name ON gfx_players(name);

-- ============================================================================
-- 2. gfx_sessions (세션/게임 단위)
-- ============================================================================
CREATE TABLE IF NOT EXISTS gfx_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- PokerGFX 세션 식별자 (Windows FileTime 기반 int64)
    session_id BIGINT NOT NULL UNIQUE,

    -- 파일 정보
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    nas_path TEXT,

    -- 세션 메타데이터
    table_type table_type NOT NULL DEFAULT 'UNKNOWN',
    event_title TEXT DEFAULT '',
    software_version TEXT DEFAULT '',
    payouts INTEGER[] DEFAULT ARRAY[]::INTEGER[],

    -- 집계 필드
    hand_count INTEGER DEFAULT 0,
    player_count INTEGER DEFAULT 0,
    total_duration_seconds INTEGER DEFAULT 0,

    -- 시간 정보
    session_created_at TIMESTAMPTZ,
    session_start_time TIMESTAMPTZ,
    session_end_time TIMESTAMPTZ,

    -- 원본 JSON 저장
    raw_json JSONB,

    -- 동기화 상태
    sync_status sync_status DEFAULT 'pending',
    sync_error TEXT,
    sync_source TEXT DEFAULT 'nas_central',

    -- 타임스탬프
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_session_id ON gfx_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_file_hash ON gfx_sessions(file_hash);
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_table_type ON gfx_sessions(table_type);
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_created_at ON gfx_sessions(session_created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_sync_status ON gfx_sessions(sync_status);
CREATE INDEX IF NOT EXISTS idx_gfx_sessions_processed_at ON gfx_sessions(processed_at DESC);

-- ============================================================================
-- 3. gfx_hands (핸드 단위)
-- ============================================================================
CREATE TABLE IF NOT EXISTS gfx_hands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 세션 참조
    session_id BIGINT NOT NULL,
    hand_num INTEGER NOT NULL,

    -- 게임 정보
    game_variant game_variant DEFAULT 'HOLDEM',
    game_class game_class DEFAULT 'FLOP',
    bet_structure bet_structure DEFAULT 'NOLIMIT',

    -- 시간 정보
    duration_seconds INTEGER DEFAULT 0,
    start_time TIMESTAMPTZ,
    recording_offset_iso TEXT,
    recording_offset_seconds BIGINT,

    -- 게임 설정
    num_boards INTEGER DEFAULT 1,
    run_it_num_times INTEGER DEFAULT 1,
    ante_amt INTEGER DEFAULT 0,
    bomb_pot_amt INTEGER DEFAULT 0,
    description TEXT DEFAULT '',

    -- 블라인드 정보 (JSONB)
    blinds JSONB DEFAULT '{}'::JSONB,
    stud_limits JSONB DEFAULT '{}'::JSONB,

    -- 집계 필드
    pot_size INTEGER DEFAULT 0,
    player_count INTEGER DEFAULT 0,
    showdown_count INTEGER DEFAULT 0,
    event_count INTEGER DEFAULT 0,

    -- 보드 카드
    board_cards TEXT[] DEFAULT ARRAY[]::TEXT[],

    -- 승자 정보
    winner_name TEXT,
    winner_seat INTEGER,

    -- 타임스탬프
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- 복합 유니크
    CONSTRAINT uq_gfx_hands_session_num UNIQUE (session_id, hand_num)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_gfx_hands_session ON gfx_hands(session_id);
CREATE INDEX IF NOT EXISTS idx_gfx_hands_start ON gfx_hands(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_gfx_hands_variant ON gfx_hands(game_variant);
CREATE INDEX IF NOT EXISTS idx_gfx_hands_pot_size ON gfx_hands(pot_size DESC);
CREATE INDEX IF NOT EXISTS idx_gfx_hands_duration ON gfx_hands(duration_seconds DESC);
CREATE INDEX IF NOT EXISTS idx_gfx_hands_board_cards ON gfx_hands USING GIN (board_cards);

-- ============================================================================
-- 4. gfx_hand_players (핸드별 플레이어)
-- ============================================================================
CREATE TABLE IF NOT EXISTS gfx_hand_players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 참조
    hand_id UUID NOT NULL REFERENCES gfx_hands(id) ON DELETE CASCADE,
    player_id UUID REFERENCES gfx_players(id) ON DELETE SET NULL,

    -- 시트 정보
    seat_num INTEGER NOT NULL CHECK (seat_num BETWEEN 1 AND 10),
    player_name TEXT NOT NULL,

    -- 홀 카드
    hole_cards TEXT[] DEFAULT ARRAY[]::TEXT[],
    has_shown BOOLEAN DEFAULT FALSE,

    -- 스택 정보
    start_stack_amt DECIMAL(18,2),
    end_stack_amt DECIMAL(18,2),
    cumulative_winnings_amt DECIMAL(18,2),
    blind_bet_straddle_amt INTEGER DEFAULT 0,

    -- 상태
    sitting_out BOOLEAN DEFAULT FALSE,
    elimination_rank INTEGER DEFAULT -1,
    is_winner BOOLEAN DEFAULT FALSE,

    -- 플레이어 통계
    vpip_percent NUMERIC(5,2) DEFAULT 0,
    preflop_raise_percent NUMERIC(5,2) DEFAULT 0,
    aggression_frequency_percent NUMERIC(5,2) DEFAULT 0,
    went_to_showdown_percent NUMERIC(5,2) DEFAULT 0,

    -- 타임스탬프
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- 복합 유니크
    CONSTRAINT uq_gfx_hand_players_seat UNIQUE (hand_id, seat_num)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_gfx_hand_players_hand ON gfx_hand_players(hand_id);
CREATE INDEX IF NOT EXISTS idx_gfx_hand_players_player ON gfx_hand_players(player_id);
CREATE INDEX IF NOT EXISTS idx_gfx_hand_players_winner ON gfx_hand_players(is_winner) WHERE is_winner = TRUE;
CREATE INDEX IF NOT EXISTS idx_gfx_hand_players_shown ON gfx_hand_players(has_shown) WHERE has_shown = TRUE;
CREATE INDEX IF NOT EXISTS idx_gfx_hand_players_cards ON gfx_hand_players USING GIN (hole_cards);

-- ============================================================================
-- 5. gfx_events (액션/이벤트)
-- ============================================================================
CREATE TABLE IF NOT EXISTS gfx_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 핸드 참조
    hand_id UUID NOT NULL REFERENCES gfx_hands(id) ON DELETE CASCADE,

    -- 이벤트 정보
    event_order INTEGER NOT NULL,
    event_type event_type NOT NULL,
    player_num INTEGER DEFAULT 0,

    -- 베팅/팟 정보
    bet_amt INTEGER DEFAULT 0,
    pot INTEGER DEFAULT 0,

    -- 보드 카드 (BOARD_CARD 이벤트)
    board_cards TEXT,
    board_num INTEGER DEFAULT 0,

    -- Draw 게임용
    num_cards_drawn INTEGER DEFAULT 0,

    -- 시간
    event_time TIMESTAMPTZ,

    -- 추가 데이터
    extra_data JSONB,

    -- 타임스탬프
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- 복합 유니크
    CONSTRAINT uq_gfx_events_order UNIQUE (hand_id, event_order)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_gfx_events_hand ON gfx_events(hand_id);
CREATE INDEX IF NOT EXISTS idx_gfx_events_type ON gfx_events(event_type);
CREATE INDEX IF NOT EXISTS idx_gfx_events_order ON gfx_events(hand_id, event_order);
CREATE INDEX IF NOT EXISTS idx_gfx_events_board ON gfx_events(event_type) WHERE event_type = 'BOARD_CARD';

-- ============================================================================
-- 6. hand_grades (핸드 등급)
-- ============================================================================
CREATE TABLE IF NOT EXISTS hand_grades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 핸드 참조
    hand_id UUID NOT NULL REFERENCES gfx_hands(id) ON DELETE CASCADE,

    -- 등급 (A/B/C)
    grade CHAR(1) NOT NULL CHECK (grade IN ('A', 'B', 'C')),

    -- 등급 조건
    has_premium_hand BOOLEAN DEFAULT FALSE,
    has_long_playtime BOOLEAN DEFAULT FALSE,
    has_premium_board_combo BOOLEAN DEFAULT FALSE,
    conditions_met INTEGER NOT NULL CHECK (conditions_met BETWEEN 0 AND 3),

    -- 방송 적격성
    broadcast_eligible BOOLEAN DEFAULT FALSE,

    -- 편집 포인트 제안
    suggested_edit_start_offset INTEGER,
    edit_start_confidence NUMERIC(3,2),

    -- 등급 부여 정보
    graded_by TEXT,
    graded_at TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT,

    -- 타임스탬프
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- 유니크 제약
    CONSTRAINT uq_hand_grade UNIQUE (hand_id)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_hand_grades_grade ON hand_grades(grade);
CREATE INDEX IF NOT EXISTS idx_hand_grades_eligible ON hand_grades(broadcast_eligible) WHERE broadcast_eligible = TRUE;
CREATE INDEX IF NOT EXISTS idx_hand_grades_hand_id ON hand_grades(hand_id);

-- ============================================================================
-- 7. sync_log (동기화 로그)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sync_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 파일 정보
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size_bytes BIGINT,

    -- PC 정보
    gfx_pc_id TEXT,
    session_id BIGINT,

    -- 작업 정보
    operation TEXT NOT NULL,
    status TEXT DEFAULT 'processing',

    -- 결과
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    error_message TEXT,
    error_details JSONB,
    retry_count INTEGER DEFAULT 0,

    -- 성능 측정
    duration_ms INTEGER,

    -- 타임스탬프
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_sync_log_hash ON sync_log(file_hash);
CREATE INDEX IF NOT EXISTS idx_sync_log_status ON sync_log(status);
CREATE INDEX IF NOT EXISTS idx_sync_log_created ON sync_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_log_pc ON sync_log(gfx_pc_id);
CREATE INDEX IF NOT EXISTS idx_sync_log_session ON sync_log(session_id);

-- ============================================================================
-- 8. updated_at 자동 갱신 트리거
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 트리거 적용
DROP TRIGGER IF EXISTS update_gfx_players_updated_at ON gfx_players;
CREATE TRIGGER update_gfx_players_updated_at
    BEFORE UPDATE ON gfx_players
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_gfx_sessions_updated_at ON gfx_sessions;
CREATE TRIGGER update_gfx_sessions_updated_at
    BEFORE UPDATE ON gfx_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_gfx_hands_updated_at ON gfx_hands;
CREATE TRIGGER update_gfx_hands_updated_at
    BEFORE UPDATE ON gfx_hands
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 9. Views (PRD Section 5)
-- ============================================================================

-- v_recent_hands: 최근 핸드 + 등급 정보 뷰
CREATE OR REPLACE VIEW v_recent_hands AS
SELECT
    h.id,
    h.session_id,
    h.hand_num,
    h.game_variant,
    h.bet_structure,
    h.duration_seconds,
    h.start_time,
    h.pot_size,
    h.board_cards,
    h.winner_name,
    h.player_count,
    h.showdown_count,
    s.table_type,
    s.event_title,
    g.grade,
    g.broadcast_eligible,
    g.conditions_met
FROM gfx_hands h
LEFT JOIN gfx_sessions s ON h.session_id = s.session_id
LEFT JOIN hand_grades g ON h.id = g.hand_id
ORDER BY h.start_time DESC;

-- v_showdown_players: 쇼다운 플레이어 (홀카드 공개)
CREATE OR REPLACE VIEW v_showdown_players AS
SELECT
    hp.id,
    hp.hand_id,
    hp.player_name,
    hp.seat_num,
    hp.hole_cards,
    hp.start_stack_amt,
    hp.end_stack_amt,
    hp.cumulative_winnings_amt,
    hp.is_winner,
    h.hand_num,
    h.board_cards,
    h.pot_size,
    h.session_id
FROM gfx_hand_players hp
JOIN gfx_hands h ON hp.hand_id = h.id
WHERE hp.has_shown = TRUE
ORDER BY h.start_time DESC, hp.seat_num;

-- v_session_summary: 세션 요약 통계
CREATE OR REPLACE VIEW v_session_summary AS
SELECT
    s.id,
    s.session_id,
    s.file_name,
    s.table_type,
    s.event_title,
    s.hand_count,
    s.total_duration_seconds,
    s.session_created_at,
    s.sync_status,
    COUNT(CASE WHEN g.grade = 'A' THEN 1 END) AS grade_a_count,
    COUNT(CASE WHEN g.grade = 'B' THEN 1 END) AS grade_b_count,
    COUNT(CASE WHEN g.grade = 'C' THEN 1 END) AS grade_c_count,
    COUNT(CASE WHEN g.broadcast_eligible THEN 1 END) AS eligible_count
FROM gfx_sessions s
LEFT JOIN gfx_hands h ON s.session_id = h.session_id
LEFT JOIN hand_grades g ON h.id = g.hand_id
GROUP BY s.id, s.session_id, s.file_name, s.table_type,
         s.event_title, s.hand_count, s.total_duration_seconds,
         s.session_created_at, s.sync_status
ORDER BY s.session_created_at DESC;

-- ============================================================================
-- 10. 유틸리티 함수 (PRD Section 6)
-- ============================================================================

-- 플레이어 해시 생성
CREATE OR REPLACE FUNCTION generate_player_hash(p_name TEXT, p_long_name TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN md5(LOWER(TRIM(COALESCE(p_name, ''))) || ':' || LOWER(TRIM(COALESCE(p_long_name, ''))));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ISO 8601 Duration 파싱
CREATE OR REPLACE FUNCTION parse_iso8601_duration(duration TEXT)
RETURNS NUMERIC AS $$
DECLARE
    hours_match TEXT[];
    minutes_match TEXT[];
    seconds_match TEXT[];
    total_seconds NUMERIC := 0;
BEGIN
    IF duration IS NULL OR duration = '' THEN
        RETURN 0;
    END IF;

    hours_match := regexp_match(duration, '(\d+(?:\.\d+)?)H', 'i');
    IF hours_match IS NOT NULL THEN
        total_seconds := total_seconds + (hours_match[1]::NUMERIC * 3600);
    END IF;

    minutes_match := regexp_match(duration, 'T.*?(\d+(?:\.\d+)?)M', 'i');
    IF minutes_match IS NOT NULL THEN
        total_seconds := total_seconds + (minutes_match[1]::NUMERIC * 60);
    END IF;

    seconds_match := regexp_match(duration, '(\d+(?:\.\d+)?)S', 'i');
    IF seconds_match IS NOT NULL THEN
        total_seconds := total_seconds + seconds_match[1]::NUMERIC;
    END IF;

    RETURN total_seconds;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 세션 통계 업데이트
CREATE OR REPLACE FUNCTION update_session_stats(p_session_id BIGINT)
RETURNS VOID AS $$
BEGIN
    UPDATE gfx_sessions
    SET
        hand_count = (
            SELECT COUNT(*) FROM gfx_hands WHERE session_id = p_session_id
        ),
        total_duration_seconds = (
            SELECT COALESCE(SUM(duration_seconds), 0)
            FROM gfx_hands WHERE session_id = p_session_id
        ),
        session_start_time = (
            SELECT MIN(start_time) FROM gfx_hands WHERE session_id = p_session_id
        ),
        session_end_time = (
            SELECT MAX(start_time + (duration_seconds || ' seconds')::INTERVAL)
            FROM gfx_hands WHERE session_id = p_session_id
        ),
        updated_at = NOW()
    WHERE session_id = p_session_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 완료 메시지
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE 'GFX JSON 정규화 테이블 마이그레이션 완료 (v2.0.0)';
    RAISE NOTICE '생성된 테이블: gfx_players, gfx_sessions, gfx_hands, gfx_hand_players, gfx_events, hand_grades, sync_log';
    RAISE NOTICE '생성된 뷰: v_recent_hands, v_showdown_players, v_session_summary';
    RAISE NOTICE 'SSOT: C:\claude\automation_schema\docs\02-GFX-JSON-DB.md';
END $$;
