# GFX Sync Agent - 스키마 정합성 분석 보고서

**Date**: 2026-01-16 (v2.0)
**Project**: gfx_json (PokerGFX JSON to Supabase Sync)
**Author**: Schema Analysis Agent
**SSOT**: `C:\claude\automation_schema\docs\02-GFX-JSON-DB.md`

---

## Executive Summary

### 2026-01-16 스키마 정합성 작업 완료

**3개 소스 동기화 완료**:

| 소스 | 역할 | 상태 |
|------|------|:----:|
| PRD 문서 (`02-GFX-JSON-DB.md`) | **SSOT** (Single Source of Truth) | 기준 |
| 로컬 Migration SQL | 실행 가능한 DDL | ✅ PRD 일치 |
| Python 모델/코드 | 애플리케이션 레이어 | ✅ PRD 일치 |

---

## 1. 수정 완료 항목

### 1.1 Migration SQL (`001_create_normalized_tables.sql`)

**v1.0 → v2.0 업데이트**:

| 항목 | 이전 | 수정 후 |
|------|------|---------|
| ENUM Types | 없음 | 6개 추가 (table_type, game_variant 등) |
| gfx_sessions | 기본 필드만 | nas_path, sync_status, session_start/end_time 추가 |
| gfx_hands | recording_offset_start | recording_offset_iso + recording_offset_seconds |
| gfx_hands | 누락 필드 다수 | bomb_pot_amt, blinds (JSONB), showdown_count 등 |
| gfx_hand_players | 기본 필드만 | player_name, has_shown, blind_bet_straddle_amt 등 |
| gfx_events | amount | bet_amt (PRD 일치) |
| hand_grades | 없음 | **신규 테이블** 추가 |
| Views | 없음 | 3개 추가 (v_recent_hands, v_showdown_players, v_session_summary) |
| Functions | 기본만 | parse_iso8601_duration, update_session_stats 추가 |

### 1.2 Python 모델 (`player.py`)

**HandPlayerRecord 필드 추가**:

```python
# 추가된 필드
has_shown: bool = False
blind_bet_straddle_amt: int = 0
went_to_showdown_percent: float | None = None
elimination_rank: int = -1  # (기본값 0 → -1 변경)
```

### 1.3 Transformer (`player_transformer.py`)

**transform_for_hand() 업데이트**:

```python
# 추가된 매핑
has_shown=len(hole_cards) > 0,
blind_bet_straddle_amt=data.get("BlindBetStraddleAmt", 0) or 0,
went_to_showdown_percent=data.get("WentToShowDownPercent"),
```

---

## 2. 테이블별 스키마 비교

### 2.1 gfx_sessions

| 필드 | PRD | Migration SQL | 상태 |
|------|:---:|:-------------:|:----:|
| id (UUID PK) | ✅ | ✅ | 일치 |
| session_id (BIGINT UNIQUE) | ✅ | ✅ | 일치 |
| file_name | ✅ | ✅ | 일치 |
| file_hash (UNIQUE) | ✅ | ✅ | 일치 |
| nas_path | ✅ | ✅ | 일치 |
| table_type (ENUM) | ✅ | ✅ | 일치 |
| event_title | ✅ | ✅ | 일치 |
| software_version | ✅ | ✅ | 일치 |
| payouts (INTEGER[]) | ✅ | ✅ | 일치 |
| hand_count | ✅ | ✅ | 일치 |
| player_count | ✅ | ✅ | 일치 |
| total_duration_seconds | ✅ | ✅ | 일치 |
| session_created_at | ✅ | ✅ | 일치 |
| session_start_time | ✅ | ✅ | 일치 |
| session_end_time | ✅ | ✅ | 일치 |
| raw_json (JSONB) | ✅ | ✅ | 일치 |
| sync_status (ENUM) | ✅ | ✅ | 일치 |
| sync_error | ✅ | ✅ | 일치 |
| processed_at | ✅ | ✅ | 일치 |

### 2.2 gfx_hands

| 필드 | PRD | Migration SQL | 상태 |
|------|:---:|:-------------:|:----:|
| id (UUID PK) | ✅ | ✅ | 일치 |
| session_id (BIGINT) | ✅ | ✅ | 일치 |
| hand_num | ✅ | ✅ | 일치 |
| game_variant (ENUM) | ✅ | ✅ | 일치 |
| game_class (ENUM) | ✅ | ✅ | 일치 |
| bet_structure (ENUM) | ✅ | ✅ | 일치 |
| duration_seconds | ✅ | ✅ | 일치 |
| start_time | ✅ | ✅ | 일치 |
| recording_offset_iso | ✅ | ✅ | 일치 |
| recording_offset_seconds | ✅ | ✅ | 일치 |
| num_boards | ✅ | ✅ | 일치 |
| run_it_num_times | ✅ | ✅ | 일치 |
| ante_amt | ✅ | ✅ | 일치 |
| bomb_pot_amt | ✅ | ✅ | 일치 |
| description | ✅ | ✅ | 일치 |
| blinds (JSONB) | ✅ | ✅ | 일치 |
| stud_limits (JSONB) | ✅ | ✅ | 일치 |
| pot_size | ✅ | ✅ | 일치 |
| player_count | ✅ | ✅ | 일치 |
| showdown_count | ✅ | ✅ | 일치 |
| board_cards (TEXT[]) | ✅ | ✅ | 일치 |
| winner_name | ✅ | ✅ | 일치 |
| winner_seat | ✅ | ✅ | 일치 |

### 2.3 gfx_hand_players

| 필드 | PRD | Migration SQL | Python 모델 | 상태 |
|------|:---:|:-------------:|:-----------:|:----:|
| id (UUID PK) | ✅ | ✅ | ✅ | 일치 |
| hand_id (UUID FK) | ✅ | ✅ | ✅ | 일치 |
| player_id (UUID FK) | ✅ | ✅ | ✅ | 일치 |
| seat_num | ✅ | ✅ | ✅ | 일치 |
| player_name | ✅ | ✅ | ✅ | 일치 |
| hole_cards (TEXT[]) | ✅ | ✅ | ✅ | 일치 |
| has_shown | ✅ | ✅ | ✅ | 일치 |
| start_stack_amt | ✅ | ✅ | ✅ | 일치 |
| end_stack_amt | ✅ | ✅ | ✅ | 일치 |
| cumulative_winnings_amt | ✅ | ✅ | ✅ | 일치 |
| blind_bet_straddle_amt | ✅ | ✅ | ✅ | 일치 |
| sitting_out | ✅ | ✅ | ✅ | 일치 |
| elimination_rank | ✅ | ✅ | ✅ | 일치 |
| is_winner | ✅ | ✅ | ✅ | 일치 |
| vpip_percent | ✅ | ✅ | ✅ | 일치 |
| preflop_raise_percent | ✅ | ✅ | ✅ | 일치 |
| aggression_frequency_percent | ✅ | ✅ | ✅ | 일치 |
| went_to_showdown_percent | ✅ | ✅ | ✅ | 일치 |

### 2.4 gfx_events

| 필드 | PRD | Migration SQL | 상태 |
|------|:---:|:-------------:|:----:|
| id (UUID PK) | ✅ | ✅ | 일치 |
| hand_id (UUID FK) | ✅ | ✅ | 일치 |
| event_order | ✅ | ✅ | 일치 |
| event_type (ENUM) | ✅ | ✅ | 일치 |
| player_num | ✅ | ✅ | 일치 |
| bet_amt | ✅ | ✅ | 일치 |
| pot | ✅ | ✅ | 일치 |
| board_cards | ✅ | ✅ | 일치 |
| board_num | ✅ | ✅ | 일치 |
| num_cards_drawn | ✅ | ✅ | 일치 |
| event_time | ✅ | ✅ | 일치 |

### 2.5 hand_grades (신규)

| 필드 | PRD | Migration SQL | 상태 |
|------|:---:|:-------------:|:----:|
| id (UUID PK) | ✅ | ✅ | 일치 |
| hand_id (UUID FK) | ✅ | ✅ | 일치 |
| grade (A/B/C) | ✅ | ✅ | 일치 |
| has_premium_hand | ✅ | ✅ | 일치 |
| has_long_playtime | ✅ | ✅ | 일치 |
| has_premium_board_combo | ✅ | ✅ | 일치 |
| conditions_met | ✅ | ✅ | 일치 |
| broadcast_eligible | ✅ | ✅ | 일치 |
| suggested_edit_start_offset | ✅ | ✅ | 일치 |
| graded_by | ✅ | ✅ | 일치 |
| graded_at | ✅ | ✅ | 일치 |

---

## 3. ENUM Types 정의

Migration SQL에 추가된 ENUM 타입:

```sql
-- table_type: FEATURE_TABLE, MAIN_TABLE, FINAL_TABLE, SIDE_TABLE, UNKNOWN
-- game_variant: HOLDEM, OMAHA, OMAHA_HILO, STUD, STUD_HILO, RAZZ, DRAW, MIXED
-- game_class: FLOP, STUD, DRAW, MIXED
-- bet_structure: NOLIMIT, POTLIMIT, LIMIT, SPREAD_LIMIT
-- event_type: FOLD, CHECK, CALL, BET, RAISE, ALL_IN, BOARD_CARD, ANTE, BLIND, STRADDLE, BRING_IN, MUCK, SHOW, WIN
-- sync_status: pending, synced, updated, failed, archived
```

---

## 4. Views 정의

Migration SQL에 추가된 뷰:

| 뷰 | 목적 |
|----|------|
| `v_recent_hands` | 최근 핸드 + 등급 정보 조인 |
| `v_showdown_players` | 쇼다운 플레이어 (홀카드 공개) |
| `v_session_summary` | 세션 요약 통계 (등급별 카운트) |

---

## 5. 수정된 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `migrations/001_create_normalized_tables.sql` | v2.0 전면 재작성 (PRD 일치) |
| `src/sync_agent/models/player.py` | HandPlayerRecord 필드 추가 |
| `src/sync_agent/transformers/player_transformer.py` | 새 필드 매핑 추가 |

---

## 6. 다음 단계

### 필수 작업

1. **Supabase DB에 Migration 적용**
   ```bash
   supabase db push
   ```

2. **기존 컬럼과 호환성 확인**
   - 기존 DB에 이미 데이터가 있는 경우 ALTER TABLE 필요

3. **코드 테스트**
   ```bash
   pytest tests/ -v
   ```

### 선택 작업

- RLS 정책 적용 (PRD Section 8 참조)
- Dashboard와 Views 연동

---

## 참조 문서

| 문서 | 경로 |
|------|------|
| **PRD (SSOT)** | `C:\claude\automation_schema\docs\02-GFX-JSON-DB.md` |
| Migration SQL | `C:\claude\gfx_json\migrations\001_create_normalized_tables.sql` |
| Player 모델 | `C:\claude\gfx_json\src\sync_agent\models\player.py` |
| Player Transformer | `C:\claude\gfx_json\src\sync_agent\transformers\player_transformer.py` |

---

**End of Report**
