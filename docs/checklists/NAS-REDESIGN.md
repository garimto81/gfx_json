# NAS 중앙 관리 재설계 체크리스트

**PRD**: FT-0011 v3.0
**시작일**: 2026-01-13
**상태**: 진행 중

---

## Phase 1: 인프라 계층 ✅

- [x] `config/settings.py` - 환경 변수 기반 단일 설정 (11 tests)
- [x] `queue/offline_queue.py` - aiosqlite + Dead Letter Queue (17 tests)
- [x] `db/supabase_client.py` - httpx + Rate Limit 예외 (22 tests)

## Phase 2: 핵심 로직 🔄

- [x] `core/json_parser.py` - 파싱 + 해시 생성 (23 tests)
- [x] `queue/batch_queue.py` - 인메모리 배치 큐 (6 tests)
- [ ] `core/sync_service.py` - 지수 백오프 포함 ⏳ **다음 작업**

## Phase 3: 감시자 계층

- [ ] `watcher/base.py` - FileWatcher Protocol
- [ ] `watcher/registry.py` - PC 레지스트리 관리
- [ ] `watcher/polling_watcher.py` - watchdog 폴링

## Phase 4: 오케스트레이션

- [ ] `core/agent.py` - SyncAgent 오케스트레이터
- [ ] `main.py` - CLI 진입점, 시그널 핸들링

## Phase 5: 운영

- [ ] `health/healthcheck.py` - Docker 헬스체크 HTTP 서버
- [ ] `Dockerfile.agent` 업데이트
- [ ] `docker-compose.yml` 업데이트

## 정리 작업

- [ ] 기존 코드 삭제
  - [ ] `tray_app.py`
  - [ ] `settings_dialog.py`
  - [ ] `file_watcher.py` (watchfiles 버전)
  - [ ] `config.py` (3개 클래스 버전)
  - [ ] `local_queue.py` (sqlite3 버전)
  - [ ] `sync_service.py` (이중 클래스 버전)
- [ ] `pyproject.toml` 의존성 정리
- [ ] 테스트 파일 정리

---

## 생성된 파일 구조

```
src/sync_agent/
├── config/
│   ├── __init__.py          ✅
│   └── settings.py          ✅ (11 tests)
├── core/
│   ├── __init__.py          ✅
│   ├── json_parser.py       ✅ (23 tests)
│   ├── sync_service.py      ⏳ (다음)
│   └── agent.py             (대기)
├── db/
│   ├── __init__.py          ✅
│   └── supabase_client.py   ✅ (22 tests)
├── queue/
│   ├── __init__.py          ✅
│   ├── batch_queue.py       ✅ (6 tests)
│   └── offline_queue.py     ✅ (17 tests)
├── watcher/
│   ├── __init__.py          (대기)
│   ├── base.py              (대기)
│   ├── registry.py          (대기)
│   └── polling_watcher.py   (대기)
├── health/
│   ├── __init__.py          (대기)
│   └── healthcheck.py       (대기)
└── main.py                  (대기)
```

---

## 테스트 현황

| 파일 | 테스트 수 | 상태 |
|------|----------|------|
| `test_settings.py` | 11 | ✅ |
| `test_offline_queue.py` | 17 | ✅ |
| `test_supabase_client.py` | 22 | ✅ |
| `test_json_parser.py` | 23 | ✅ |
| `test_batch_queue.py` | 6 | ✅ |
| `test_file_watcher.py` | 5 | ✅ (기존) |
| `test_local_queue.py` | 5 | ✅ (기존) |
| **총계** | **89** | ✅ |

### 백업된 테스트 (재작성 필요)

`_backup_tests/` 폴더로 이동:
- `test_integration.py` - 통합 테스트 (새 구조로 재작성 필요)
- `test_sync_service.py` - SyncService 테스트 (새 버전으로 재작성)
- `test_tray_app.py` - GUI 테스트 (삭제 예정)

---

## 다음 세션 재개 방법

```powershell
# 1. 현재 테스트 상태 확인
cd C:\claude\gfx_json
python -m pytest tests/test_settings.py tests/test_offline_queue.py tests/test_supabase_client.py tests/test_json_parser.py tests/test_batch_queue.py -v

# 2. 다음 작업: core/sync_service.py 구현
# PRD: docs/gfx_supabase_sync.md 섹션 5.3 참조
```

---

## 의존성 설치 확인

```bash
pip install pydantic-settings aiosqlite httpx watchdog
```
