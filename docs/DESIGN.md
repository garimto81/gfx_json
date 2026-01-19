# FT-0011: 상세 설계 문서

## 1. 개요

NAS JSON → Supabase 최적화 동기화 시스템의 상세 설계.

**핵심 목표**:
- 파일 감지 지연: ~2초 → **~1ms** (watchfiles)
- 새 파일 동기화: ~2.5초 → **~500ms**
- CPU 사용률: 높음 → **< 1%**

---

## 2. 아키텍처

### 2.1 컴포넌트 다이어그램

```
┌──────────────────────────────────────────────────────────────────┐
│                        SyncAgent (main.py)                        │
│                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  WatchfilesWatcher│  │  SyncService    │  │  LocalQueue     │  │
│  │  (file_watcher.py)│  │  (sync_service) │  │  (local_queue)  │  │
│  │                   │  │                 │  │                 │  │
│  │  - awatch()       │  │  - sync_file()  │  │  - SQLite 기반  │  │
│  │  - Change.added   │──▶  - batch_queue  │  │  - 오프라인 큐  │  │
│  │  - Change.modified│  │  - upsert()     │◀─│  - 재시도 관리  │  │
│  └─────────────────┘  └────────┬────────┘  └─────────────────┘  │
│                                │                                  │
│                       ┌────────┴────────┐                        │
│                       │   BatchQueue    │                        │
│                       │ (batch_queue.py)│                        │
│                       │                 │                        │
│                       │ - max_size: 500 │                        │
│                       │ - interval: 5s  │                        │
│                       └─────────────────┘                        │
└──────────────────────────────────────────────────────────────────┘
                                │
                                │ HTTPS
                                ▼
                    ┌─────────────────────────┐
                    │        Supabase         │
                    │    gfx_sessions 테이블   │
                    │  (file_hash UNIQUE)     │
                    └─────────────────────────┘
```

### 2.2 데이터 흐름

```
┌──────────┐   Change.added    ┌────────────┐   단건 Upsert   ┌──────────┐
│  JSON    │──────────────────▶│ SyncService│───────────────▶│ Supabase │
│  파일    │                   │            │                 │          │
└──────────┘   Change.modified │            │                 └──────────┘
      │        ────────────────▶│            │                      ▲
      │                        │ BatchQueue │   배치 Upsert        │
      │                        │ (500건/5초)│──────────────────────┘
      │                        └────────────┘
      │                              ▲
      │   네트워크 실패 시            │
      └───────────────────────▶ LocalQueue ─────────────────────────┘
                                 (SQLite)      복구 후 배치 처리
```

---

## 3. 모듈 설계

### 3.1 WatchfilesWatcher

**역할**: OS 네이티브 API를 통한 파일 변경 감지

**인터페이스**:
```python
class WatchfilesWatcher:
    def __init__(
        self,
        watch_path: str,
        on_created: Callable[[str], Coroutine],
        on_modified: Callable[[str], Coroutine],
        file_pattern: str = "*.json",
    ) -> None: ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

**핵심 로직**:
1. `watchfiles.awatch()` 사용 (async)
2. `Change.added` → `on_created` 콜백
3. `Change.modified` → `on_modified` 콜백
4. 파일 패턴 필터링 (`*.json`)

### 3.2 BatchQueue

**역할**: 배치 처리를 위한 인메모리 큐

**인터페이스**:
```python
@dataclass
class BatchQueue:
    max_size: int = 500
    flush_interval: float = 5.0

    async def add(self, record: dict) -> list[dict] | None: ...
    async def flush(self) -> list[dict]: ...
    @property
    def pending_count(self) -> int: ...
```

**플러시 조건**:
- `len(items) >= max_size` (500건)
- `time.time() - last_flush >= flush_interval` (5초)

### 3.3 SyncService

**역할**: 동기화 로직 (실시간 + 배치)

**인터페이스**:
```python
class SyncService:
    def __init__(self, settings: SyncAgentSettings, local_queue: LocalQueue): ...

    async def sync_file(self, path: str, event_type: str) -> None: ...
    async def process_offline_queue(self) -> None: ...
    async def flush_batch_queue(self) -> None: ...
```

**실시간 경로** (Change.added):
```python
async def sync_file(self, path: str, event_type: str):
    record = self._parse_json(path)

    if event_type == "created":
        # 즉시 단건 upsert
        await self._upsert_single(record)
    else:
        # 배치 큐에 추가
        batch = await self.batch_queue.add(record)
        if batch:
            await self._upsert_batch(batch)
```

### 3.4 LocalQueue

**역할**: SQLite 기반 오프라인 큐 (장애 복구)

**인터페이스**:
```python
class LocalQueue:
    def __init__(self, db_path: str): ...

    async def enqueue(self, record: dict, file_path: str) -> None: ...
    async def dequeue_batch(self, limit: int = 50) -> list[dict]: ...
    async def mark_completed(self, ids: list[int]) -> None: ...
    async def mark_failed(self, id: int) -> None: ...
    async def get_pending_count(self) -> int: ...
```

**SQLite 스키마**:
```sql
CREATE TABLE pending_sync (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    record_json TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_attempt TIMESTAMP
);
```

### 3.5 SyncAgentSettings

**역할**: 설정 관리 (pydantic-settings)

```python
class SyncAgentSettings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_key: str

    # 경로
    gfx_watch_path: str = "C:/GFX/output"
    queue_db_path: str = "C:/GFX/sync_queue/pending.db"

    # 배치
    batch_size: int = 500
    flush_interval: float = 5.0

    # 큐
    queue_process_interval: int = 60
    max_retries: int = 5

    model_config = SettingsConfigDict(env_prefix="GFX_SYNC_")
```

---

## 4. 에러 처리 전략

### 4.1 네트워크 장애

```
Supabase 연결 실패
    │
    ▼
LocalQueue에 저장 (SQLite)
    │
    ▼
주기적 재시도 (60초마다)
    │
    ├── 성공 → mark_completed()
    │
    └── 실패 → retry_count++
           │
           ├── retry_count < max_retries → 다음 주기에 재시도
           │
           └── retry_count >= max_retries → 로그 경고, 수동 처리 필요
```

### 4.2 파일 파싱 에러

```python
try:
    record = self._parse_json(path)
except json.JSONDecodeError as e:
    logger.error(f"JSON 파싱 실패: {path}, {e}")
    # 별도 에러 로그에 기록, 동기화 스킵
```

### 4.3 중복 파일 (file_hash 충돌)

- `.upsert(on_conflict="file_hash")` 사용
- 기존 레코드 자동 업데이트
- 에러 없이 처리 완료

---

## 5. 성능 최적화

### 5.1 배치 처리

| 방식 | 100건 처리 시간 | 이유 |
|------|---------------|------|
| 개별 insert | ~50초 | 100회 HTTP 요청 |
| 배치 upsert | ~8초 | 1회 HTTP 요청 |

### 5.2 watchfiles vs PollingObserver

| 항목 | PollingObserver | watchfiles |
|------|-----------------|------------|
| 감지 방식 | 2초마다 스캔 | OS 네이티브 이벤트 |
| CPU 사용 | ~5% | **< 0.1%** |
| 감지 지연 | ~2000ms | **~1ms** |
| 구현 | Python | Rust (Notify) |

---

## 6. 파일 구조

```
C:\claude\gfx_json\
├── src/
│   └── sync_agent/
│       ├── __init__.py
│       ├── config.py          # 설정 (SyncAgentSettings)
│       ├── file_watcher.py    # WatchfilesWatcher
│       ├── batch_queue.py     # BatchQueue
│       ├── sync_service.py    # SyncService
│       ├── local_queue.py     # LocalQueue (SQLite)
│       └── main.py            # SyncAgent 진입점
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # pytest fixtures
│   ├── test_batch_queue.py
│   ├── test_file_watcher.py
│   ├── test_sync_service.py
│   ├── test_local_queue.py
│   └── test_integration.py
├── docs/
│   ├── DESIGN.md              # 이 문서
│   └── TDD_CHECKLIST.md       # TDD 체크리스트
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 7. 의존성

```
watchfiles>=0.21.0      # Rust 기반 파일 감시
supabase>=2.0.0         # Supabase Python 클라이언트
pydantic-settings>=2.0  # 환경 변수 설정
aiosqlite>=0.19.0       # 비동기 SQLite
pytest>=8.0             # 테스트
pytest-asyncio>=0.23    # 비동기 테스트
pytest-cov>=4.0         # 커버리지
```

---

## 8. 환경 변수

```env
# Supabase 연결 (필수)
GFX_SYNC_SUPABASE_URL=https://<project-ref>.supabase.co
GFX_SYNC_SUPABASE_SERVICE_KEY=eyJxxx...  # service_role key (NOT anon)

# 경로
GFX_SYNC_GFX_WATCH_PATH=C:/GFX/output
GFX_SYNC_QUEUE_DB_PATH=C:/GFX/sync_queue/pending.db

# 배치 설정
GFX_SYNC_BATCH_SIZE=500
GFX_SYNC_FLUSH_INTERVAL=5.0
GFX_SYNC_QUEUE_PROCESS_INTERVAL=60
GFX_SYNC_MAX_RETRIES=5
```

### Supabase Key 종류

| Key | 용도 | RLS |
|-----|------|-----|
| anon | 클라이언트 (브라우저) | 적용됨 |
| **service_role** | 서버 (백엔드) | **우회** |

**GFX Sync Agent는 `service_role` key를 사용합니다.**

```powershell
# Key 확인 방법
supabase projects api-keys --project-ref <project-ref>
```
