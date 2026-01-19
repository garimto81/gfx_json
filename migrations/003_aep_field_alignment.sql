-- =============================================================================
-- GFX AEP 필드 정렬 마이그레이션
-- 작성일: 2026-01-14
-- 설명: GFX_AEP_FIELD_MAPPING.md 문서와 스키마 일치화
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. gfx_hand_players 테이블 확장
-- -----------------------------------------------------------------------------

-- player_name 추가 (비정규화 - JOIN 없이 직접 접근용)
ALTER TABLE gfx_hand_players
ADD COLUMN IF NOT EXISTS player_name TEXT;

-- elimination_rank 추가 (탈락 순위, 0 = 탈락하지 않음)
ALTER TABLE gfx_hand_players
ADD COLUMN IF NOT EXISTS elimination_rank INTEGER DEFAULT 0;

-- 인덱스: 탈락자 조회 최적화
CREATE INDEX IF NOT EXISTS idx_gfx_hand_players_elimination
ON gfx_hand_players(elimination_rank) WHERE elimination_rank > 0;

-- 인덱스: 플레이어명 검색
CREATE INDEX IF NOT EXISTS idx_gfx_hand_players_name
ON gfx_hand_players(player_name);

COMMENT ON COLUMN gfx_hand_players.player_name IS '플레이어명 (비정규화, AEP 매핑용)';
COMMENT ON COLUMN gfx_hand_players.elimination_rank IS '탈락 순위 (0=미탈락, 1=1위 탈락)';

-- -----------------------------------------------------------------------------
-- 2. gfx_hands 테이블에 blinds JSONB 컬럼 추가
-- -----------------------------------------------------------------------------

-- blinds JSONB 추가 (기존 개별 컬럼과 병행)
ALTER TABLE gfx_hands
ADD COLUMN IF NOT EXISTS blinds JSONB;

COMMENT ON COLUMN gfx_hands.blinds IS 'JSONB 블라인드 정보 {"small_blind_amt", "big_blind_amt", "ante"}';

-- -----------------------------------------------------------------------------
-- 3. gfx_hands_unified 뷰 생성 (통합 접근용)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW gfx_hands_unified AS
SELECT
    h.*,
    COALESCE(
        h.blinds,
        jsonb_build_object(
            'small_blind_amt', h.small_blind,
            'big_blind_amt', h.big_blind,
            'ante', h.ante
        )
    ) AS blinds_compat
FROM gfx_hands h;

COMMENT ON VIEW gfx_hands_unified IS 'blinds JSONB 통합 뷰 (기존 컬럼과 호환)';

-- -----------------------------------------------------------------------------
-- 4. 기존 데이터 마이그레이션 (blinds JSONB 채우기)
-- -----------------------------------------------------------------------------

UPDATE gfx_hands
SET blinds = jsonb_build_object(
    'small_blind_amt', small_blind,
    'big_blind_amt', big_blind,
    'ante', ante
)
WHERE blinds IS NULL
  AND (small_blind IS NOT NULL OR big_blind IS NOT NULL);

-- =============================================================================
-- 검증 쿼리
-- =============================================================================

-- SELECT * FROM gfx_hand_players WHERE elimination_rank > 0;
-- SELECT blinds->>'big_blind_amt' FROM gfx_hands LIMIT 5;
-- SELECT * FROM gfx_hands_unified LIMIT 5;
