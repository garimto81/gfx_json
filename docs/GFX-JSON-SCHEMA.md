# GFX JSON Schema Analysis

## 1. Overview

PokerGFX 소프트웨어가 내보내는 JSON 파일의 실제 구조와 `json_parser.py`의 매핑 전략을 문서화합니다.

---

## 2. 이상적인 스키마 vs 실제 스키마

### 2.1 이상적인 스키마 (문서 명세)

PokerGFX 전체 스키마에는 다음 필드들이 정의되어 있습니다:

```json
{
  "ID": 133850499287550000,
  "CreatedDateTimeUTC": "2025-01-18T05:18:43.4285917Z",
  "EventTitle": "WSOP Main Event Day 1",
  "SoftwareVersion": "PokerGFX 3.2",
  "Type": "FEATURE_TABLE",
  "Payouts": [1000000, 500000, 250000, ...],
  "Hands": [...]
}
```

### 2.2 실제 스키마 (관찰됨)

실제 PokerGFX 소프트웨어가 내보내는 JSON 파일:

```json
{
  "EventTitle": "",
  "CreatedDateTimeUTC": "2025-01-18T05:18:43.4285917Z",
  "Hands": [
    {
      "Players": [
        {"Name": "Player1", "PlayerNum": 1, ...},
        {"Name": "Player2", "PlayerNum": 2, ...}
      ],
      ...
    }
  ]
}
```

> **주의**: PokerGFX 소프트웨어 버전에 따라 출력 필드가 다를 수 있습니다.

---

## 3. 필드 존재 여부 비교

| JSON 필드 | 문서 명세 | 실제 존재 | 추출 전략 |
|-----------|:---------:|:---------:|-----------|
| `ID` | O | **X** | 파일명에서 `GameID=` 추출 |
| `Type` | O | **X** | 기본값 `UNKNOWN` 반환 |
| `SoftwareVersion` | O | **X** | `None` 반환 (미저장) |
| `EventTitle` | O | O (빈 문자열) | 빈 문자열도 저장 |
| `CreatedDateTimeUTC` | O | O | 정상 추출 |
| `Payouts` | O | **X** | `None` 반환 (미저장) |
| `Hands[]` | O | O | 정상 추출 |
| `Hands[].Players[]` | O | O | `player_count` 계산에 사용 |

---

## 4. json_parser.py 매핑 전략

### 4.1 session_id 추출 (우선순위)

```
1. data["ID"]                    # PascalCase (문서 기준)
2. data["session_id"]            # snake_case
3. data["session"]["id"]         # nested
4. data["id"]                    # lowercase
5. 파일명에서 GameID= 추출       # fallback
```

**실제 동작**: 파일명 `PGFX_live_data_export GameID=133850499287550000.json`에서 추출

### 4.2 table_type 추출 (우선순위)

```
1. data["Type"]                  # PascalCase (문서 기준)
2. data["table_type"]            # snake_case
3. data["tableType"]             # camelCase
4. data["session"]["Type"]       # nested
5. 기본값 "UNKNOWN"              # fallback
```

**Supabase ENUM 매핑**:
- `FEATURE_TABLE`, `MAIN_TABLE`, `FINAL_TABLE`, `SIDE_TABLE`, `UNKNOWN`

### 4.3 player_count 추출

```python
# Hands 배열에서 고유 플레이어 수 계산
hands = data.get("Hands") or data.get("hands") or []
all_players = set()
for hand in hands:
    players = hand.get("Players") or hand.get("players") or []
    for player in players:
        name = player.get("Name") or player.get("name")
        if name:
            all_players.add(name)
return len(all_players)
```

### 4.4 nas_path 구성

```python
# gfx_pc_id를 nas_path에 포함
nas_path = f"/nas/{gfx_pc_id}/{path.name}"
# 예: "/nas/PC01/PGFX_live_data_export GameID=133850499287550000.json"
```

---

## 5. Supabase gfx_sessions 테이블 매핑

| Supabase 컬럼 | json_parser.py 출력 | 값 예시 |
|---------------|---------------------|---------|
| `session_id` | 파일명 GameID | `133850499287550000` |
| `file_hash` | SHA-256(content) | `abc123...` |
| `file_name` | path.name | `PGFX_live_data_export GameID=...` |
| `nas_path` | `/nas/{pc_id}/{name}` | `/nas/PC01/PGFX_...` |
| `table_type` | `UNKNOWN` (기본값) | `UNKNOWN` |
| `event_title` | 빈 문자열 | `""` |
| `software_version` | `None` | 미저장 |
| `player_count` | Hands[].Players 계산 | `9` |
| `hand_count` | len(Hands) | `25` |
| `payouts` | `None` | 미저장 |
| `raw_json` | 전체 JSON | `{...}` |

---

## 6. 검증 쿼리

### Supabase 데이터 확인

```bash
# SSH를 통한 Supabase 조회 (Docker 환경)
ssh user@host "docker exec container curl -s \
  'https://PROJECT.supabase.co/rest/v1/gfx_sessions?select=session_id,table_type,event_title,player_count,nas_path&limit=3' \
  -H 'apikey: KEY' \
  -H 'Authorization: Bearer KEY'"
```

### 기대 결과

```json
[
  {
    "session_id": 133850499287550000,
    "table_type": "UNKNOWN",
    "event_title": "",
    "player_count": 9,
    "nas_path": "/nas/PC01/PGFX_live_data_export GameID=133850499287550000.json"
  }
]
```

---

## 7. PokerGFX 설정 확인 사항

현재 PokerGFX 소프트웨어의 내보내기 옵션을 확인하여 추가 필드를 활성화할 수 있는지 검토 권장:

| 필드 | 활성화 가능 여부 | 우선순위 |
|------|:---------------:|:--------:|
| `Type` | 확인 필요 | 높음 |
| `SoftwareVersion` | 확인 필요 | 낮음 |
| `Payouts` | 확인 필요 | 중간 |

---

## 8. 변경 이력

| 날짜 | 변경 내용 | 관련 이슈 |
|------|-----------|----------|
| 2026-01-19 | 문서 생성, 실제 스키마 분석 | - |
| 2025-01-18 | `_extract_player_count()` 추가 | #6 |
| 2025-01-18 | `gfx_pc_id` → `nas_path` 통합 | #6 |
