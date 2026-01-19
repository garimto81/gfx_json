# FT-0011: NAS 중앙 관리 GFX Sync 시스템 (v3.0)

## 문서 정보

| 항목 | 내용 |
|------|------|
| **PRD ID** | FT-0011 |
| **제목** | NAS 중앙 관리 GFX JSON → Supabase 동기화 시스템 |
| **버전** | 3.0 (전면 재설계) |
| **작성일** | 2026-01-13 |
| **상태** | Draft |
| **관련 이슈** | TBD |

---

## 1. 개요

### 1.1 목적

여러 대의 GFX PC에서 생성되는 PokerGFX JSON 파일을 **NAS에서 중앙 집중식으로 수집**하여 Supabase로 동기화.

### 1.2 핵심 변경 (v2.0 → v3.0)

| 항목 | v2.0 | v3.0 |
|------|------|------|
| **배포 모드** | PC 로컬 + NAS 중앙 | **NAS 중앙만** |
| **코드베이스** | 이중화 (SyncService / CentralSyncService) | **단일화** |
| **설정 클래스** | 3개 (AppConfig, SyncAgent, Central) | **1개 (Settings)** |
| **SQLite** | 동기 (`sqlite3`) | **비동기 (`aiosqlite`)** |
| **Supabase 클라이언트** | `supabase` 패키지 | **`httpx` 직접 호출** |
| **GUI** | System Tray (pystray) | **제거** |

### 1.3 목표

| 지표 | 목표 |
|------|------|
| 파일 감지 지연 | ~2초 (SMB 폴링 한계) |
| 새 파일 동기화 | < 3초 |
| 배치 처리 (500건) | < 10초 |
| CPU 사용률 | < 1% |
| 데이터 손실 | 0건 |

---

## 2. 아키텍처

### 2.1 전체 구조

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           GFX PC Layer                                   │
│                                                                          │
│   GFX PC 1        GFX PC 2        ...        GFX PC N                   │
│   (PokerGFX)      (PokerGFX)                (PokerGFX)                  │
│       │               │                         │                        │
│       └───────────────┴─────────────────────────┘                        │
│                           │ SMB Write                                    │
└───────────────────────────┼──────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       NAS Storage Layer                                  │
│   /volume1/gfx_data/                                                     │
│   ├── config/pc_registry.json    ← PC 등록 정보 (JSON)                  │
│   ├── PC01/                      ← GFX PC 1 전용 폴더 (JSON 직접 저장)   │
│   ├── PC02/                      ← GFX PC 2 전용 폴더                   │
│   ├── ...                                                                │
│   └── _error/                    ← 파싱 실패 파일 격리                   │
└───────────────────────────┼──────────────────────────────────────────────┘
                            │ Docker Volume Mount
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Docker Container Layer                                 │
│                                                                          │
│   ┌─────────────────────────────────┐  ┌────────────────────────────┐   │
│   │   Sync Agent (Python)           │  │  Dashboard (Next.js)       │   │
│   │                                 │  │  Port 3000                 │   │
│   │   - PollingWatcher (2초)        │  │                            │   │
│   │   - SyncService                 │  │  - 실시간 현황             │   │
│   │   - BatchQueue (500건/5초)      │  │  - PC별 상태               │   │
│   │   - OfflineQueue (aiosqlite)    │  │  - 오류 목록               │   │
│   │   - SupabaseClient (httpx)      │  │  - 모니터링 지표           │   │
│   └───────────────┬─────────────────┘  └─────────────┬──────────────┘   │
│                   │                                  │                   │
└───────────────────┼──────────────────────────────────┼───────────────────┘
                    │ HTTPS                            │ Realtime
                    ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Supabase Cloud                                  │
│                                                                          │
│   ┌─────────────────────────┐  ┌─────────────────────────────────────┐  │
│   │   gfx_sessions 테이블   │  │      sync_events 테이블            │  │
│   │                         │  │      (Realtime 활성화)             │  │
│   │   UNIQUE(gfx_pc_id,     │  │                                     │  │
│   │          file_hash)     │  │   → Dashboard 실시간 업데이트      │  │
│   └─────────────────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 데이터 흐름

```
GFX PC (PokerGFX)
    │
    │ SMB Write (JSON 파일)
    ▼
NAS Storage (/volume1/gfx_data/PC01/*.json)
    │
    │ Docker Volume Mount (read-only)
    ▼
PollingWatcher (watchdog, 2초 주기)
    │
    ▼ FileEvent(path, event_type, gfx_pc_id)
    │
SyncService
    │
    ├── created → 즉시 upsert (단건)
    │
    └── modified → BatchQueue (500건/5초) → flush → upsert (배치)
    │
    └── 실패 시 → OfflineQueue (aiosqlite)
    │
    ▼
SupabaseClient (httpx)
    │
    ▼
Supabase Cloud (gfx_sessions 테이블)
```

### 2.3 모듈 구조

```
src/sync_agent/
├── __init__.py
├── main.py                  # CLI 진입점
│
├── config/
│   └── settings.py          # Settings 단일 클래스
│
├── core/
│   ├── agent.py             # SyncAgent (오케스트레이터)
│   ├── sync_service.py      # SyncService (동기화 로직)
│   └── json_parser.py       # JSON 파싱 + 해시 생성
│
├── watcher/
│   ├── base.py              # FileWatcher Protocol
│   ├── polling_watcher.py   # SMB 폴링 감시자 (watchdog)
│   └── registry.py          # PC 레지스트리 관리
│
├── queue/
│   ├── batch_queue.py       # 인메모리 배치 큐
│   └── offline_queue.py     # aiosqlite 오프라인 큐
│
├── db/
│   └── supabase_client.py   # httpx 기반 REST 클라이언트
│
└── health/
    └── healthcheck.py       # Docker 헬스체크 HTTP 서버
```

---

## 3. 요구사항

### 3.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | 여러 GFX PC 경로 동시 감시 | **HIGH** |
| FR-02 | 새 파일 (created) 즉시 동기화 | **HIGH** |
| FR-03 | 수정 파일 (modified) 배치 처리 | HIGH |
| FR-04 | 중복 파일 자동 처리 (upsert) | HIGH |
| FR-05 | 오프라인 큐 (네트워크 장애 대응) | **HIGH** |
| FR-06 | PC 레지스트리 동적 로드 | MEDIUM |
| FR-07 | 실시간 대시보드 | MEDIUM |
| FR-08 | Docker 헬스체크 | MEDIUM |

### 3.2 비기능 요구사항

| ID | 요구사항 | 목표 값 |
|----|----------|---------|
| NFR-01 | 파일 감지 지연 | < 3초 (폴링 한계) |
| NFR-02 | 동시 PC 지원 | 10대 이상 |
| NFR-03 | 배치 처리 성능 | 500건 < 10초 |
| NFR-04 | 메모리 사용량 | < 512MB |
| NFR-05 | 장애 시 데이터 손실 | 0건 |
| NFR-06 | 컨테이너 재시작 복구 | < 30초 |

---

## 4. 오류 예상 지점 분석

### 4.1 L1: GFX PC → NAS (SMB 전송)

| 오류 | 시나리오 | 탐지 | 복구 전략 |
|------|----------|------|----------|
| 네트워크 끊김 | NAS/스위치 장애 | SMB write 실패 | GFX PC 로컬 임시 저장 |
| 세션 타임아웃 | 15분 유휴 | `STATUS_SESSION_EXPIRED` | 세션 재연결 |
| 인증 실패 | 비밀번호 변경 | `STATUS_LOGON_FAILURE` | 관리자 알림 |
| 파일 충돌 | 동시 쓰기 | `STATUS_SHARING_VIOLATION` | 지수 백오프 재시도 |
| 디스크 부족 | NAS 용량 초과 | `STATUS_DISK_FULL` | 80% 임계값 알림 |

### 4.2 L2: NAS 파일 시스템

| 오류 | 시나리오 | 탐지 | 복구 전략 |
|------|----------|------|----------|
| 부분 쓰기 | 네트워크 끊김 중 쓰기 | `JSONDecodeError` | 오류 폴더 격리 |
| 인코딩 오류 | UTF-8 BOM 등 | `UnicodeDecodeError` | 인코딩 감지 변환 |
| 파일명 특수문자 | Windows 금지 문자 | `OSError` | 파일명 sanitize |
| 시간대 불일치 | PC별 시간대 차이 | mtime 불일치 | file_hash 기반 비교 |

### 4.3 L3: Docker Agent

| 오류 | 시나리오 | 탐지 | 복구 전략 |
|------|----------|------|----------|
| 폴링 누락 | 2초 내 생성→삭제 | 없음 (silent) | **시작 시 전체 스캔** |
| JSON 파싱 | 잘못된 JSON | `JSONDecodeError` | 오류 폴더 격리 |
| 메모리 부족 | 대용량 JSON, 누수 | OOM Kill | Docker restart policy |
| 배치 오버플로우 | 대량 동시 유입 | pending_count | 조기 flush |
| 중복 이벤트 | SMB 특성 | 로그 반복 | `_processed_paths` 세트 |

### 4.4 L4: Supabase 동기화

| 오류 | 시나리오 | 탐지 | 복구 전략 |
|------|----------|------|----------|
| 타임아웃 | 서버 지연 | `TimeoutException` | OfflineQueue 저장 |
| Rate Limit | 1000/s 초과 | HTTP 429 | **지수 백오프 + jitter** |
| 인증 만료 | 키 재생성 | HTTP 401 | 관리자 알림 |
| 스키마 불일치 | 필드 누락 | HTTP 400 | 레코드 격리 |
| 페이로드 초과 | > 2MB | HTTP 413 | 레코드 분할 |

### 4.5 L5: Offline Queue (SQLite)

| 오류 | 시나리오 | 탐지 | 복구 전략 |
|------|----------|------|----------|
| DB 손상 | 비정상 종료 | `DatabaseError` | DB 재생성, WAL 모드 |
| 잠금 (BUSY) | 동시 접근 | `OperationalError` | 타임아웃 증가 |
| 무한 재시도 | 영구 오류 | retry_count 누적 | **Dead Letter Queue** |
| 큐 무한 증가 | 장기 장애 | pending_count | **최대 크기 제한** |
| 재시도 폭주 | 복구 후 동시 | 요청 급증 | **jitter 추가** |

---

## 5. 상세 설계

### 5.1 Settings (단일화)

```python
# src/sync_agent/config/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """NAS Sync Agent 설정 (환경 변수 전용)."""

    model_config = SettingsConfigDict(env_prefix="GFX_SYNC_")

    # NAS 경로
    nas_base_path: str = "/app/data"
    registry_path: str = "config/pc_registry.json"
    error_folder: str = "_error"

    # Supabase
    supabase_url: str
    supabase_secret_key: str

    # 폴링
    poll_interval: float = 2.0

    # 배치
    batch_size: int = 500
    flush_interval: float = 5.0

    # 오프라인 큐
    queue_db_path: str = "/app/queue/pending.db"
    queue_process_interval: int = 60
    max_retries: int = 5
    max_queue_size: int = 10000  # 신규: 큐 크기 제한

    # Rate Limit 대응
    rate_limit_max_retries: int = 5
    rate_limit_base_delay: float = 1.0

    # 헬스체크
    health_port: int = 8080
```

### 5.2 SyncAgent (오케스트레이터)

```python
# src/sync_agent/core/agent.py

import asyncio
from typing import Protocol

class SyncAgent:
    """NAS 동기화 에이전트."""

    def __init__(
        self,
        settings: Settings,
        watcher: FileWatcher,           # DI: Protocol
        sync_service: SyncService,      # DI
        registry: PCRegistry,           # DI
    ) -> None:
        self.settings = settings
        self.watcher = watcher
        self.sync_service = sync_service
        self.registry = registry

    async def start(self) -> None:
        """에이전트 시작 - 4개 태스크 병렬 실행."""
        await asyncio.gather(
            self._scan_existing_files(),      # 시작 시 전체 스캔
            self.watcher.start(),              # 파일 감시
            self._process_offline_queue_loop(), # 오프라인 큐 처리
            self.registry.watch_changes(),     # PC 레지스트리 감시
        )

    async def _scan_existing_files(self) -> None:
        """시작 시 기존 파일 전체 스캔 (폴링 누락 방지)."""
        for pc_id, pc_info in self.registry.watched_pcs.items():
            for json_file in pc_info.watch_path.glob("**/*.json"):
                await self.sync_service.sync_file(
                    str(json_file), "created", pc_id
                )

    async def stop(self) -> None:
        """graceful shutdown."""
        await self.watcher.stop()
        await self.sync_service.flush_batch_queue()
```

### 5.3 SyncService (동기화 로직)

```python
# src/sync_agent/core/sync_service.py

from typing import Literal

class SyncService:
    """파일 동기화 서비스."""

    def __init__(
        self,
        settings: Settings,
        supabase: SupabaseClient,       # DI
        batch_queue: BatchQueue,         # DI
        offline_queue: OfflineQueue,     # DI
        json_parser: JsonParser,         # DI
    ) -> None:
        self.settings = settings
        self.supabase = supabase
        self.batch_queue = batch_queue
        self.offline_queue = offline_queue
        self.json_parser = json_parser

    async def sync_file(
        self,
        path: str,
        event_type: Literal["created", "modified"],
        gfx_pc_id: str,
    ) -> SyncResult:
        """파일 동기화."""
        try:
            record = self.json_parser.parse(path, gfx_pc_id)
        except JSONDecodeError:
            await self._move_to_error_folder(path)
            return SyncResult(success=False, error="parse_error")

        if event_type == "created":
            return await self._upsert_single(record, path)
        else:
            batch = await self.batch_queue.add(record)
            if batch:
                return await self._upsert_batch(batch)
            return SyncResult(success=True, pending=True)

    async def _upsert_single(self, record: dict, path: str) -> SyncResult:
        """단건 upsert (Rate Limit 대응 포함)."""
        for attempt in range(self.settings.rate_limit_max_retries):
            try:
                await self.supabase.upsert("gfx_sessions", [record])
                return SyncResult(success=True)
            except RateLimitError:
                wait = self._calculate_backoff(attempt)
                await asyncio.sleep(wait)
            except Exception as e:
                await self.offline_queue.enqueue(record)
                return SyncResult(success=False, error=str(e), queued=True)

        # 모든 재시도 실패
        await self.offline_queue.enqueue(record)
        return SyncResult(success=False, error="rate_limit_exceeded", queued=True)

    def _calculate_backoff(self, attempt: int) -> float:
        """지수 백오프 + jitter 계산."""
        import random
        base = self.settings.rate_limit_base_delay
        return (2 ** attempt) * base + random.uniform(0, 1)
```

### 5.4 OfflineQueue (Dead Letter Queue 포함)

```python
# src/sync_agent/queue/offline_queue.py

import aiosqlite

class OfflineQueue:
    """aiosqlite 기반 오프라인 큐 (Dead Letter Queue 포함)."""

    def __init__(self, db_path: str, max_size: int = 10000) -> None:
        self.db_path = db_path
        self.max_size = max_size
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """DB 연결 (WAL 모드)."""
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._init_tables()

    async def _init_tables(self) -> None:
        """테이블 초기화."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS pending_sync (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_json TEXT NOT NULL,
                gfx_pc_id TEXT NOT NULL,
                file_path TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_error TEXT
            )
        """)

        # Dead Letter Queue 테이블
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS dead_letter (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_json TEXT NOT NULL,
                gfx_pc_id TEXT NOT NULL,
                file_path TEXT,
                retry_count INTEGER,
                error_reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.commit()

    async def enqueue(self, record: dict, gfx_pc_id: str, file_path: str) -> int:
        """큐에 추가 (크기 제한 적용)."""
        if await self.count() >= self.max_size:
            await self._remove_oldest()

        cursor = await self._db.execute(
            "INSERT INTO pending_sync (record_json, gfx_pc_id, file_path) VALUES (?, ?, ?)",
            (json.dumps(record), gfx_pc_id, file_path)
        )
        await self._db.commit()
        return cursor.lastrowid

    async def mark_failed(self, queue_id: int, error: str) -> None:
        """실패 처리 (Dead Letter Queue 이동 포함)."""
        async with self._db.execute(
            "SELECT * FROM pending_sync WHERE id = ?", (queue_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row and row["retry_count"] >= self.max_retries:
            # Dead Letter Queue로 이동
            await self._db.execute("""
                INSERT INTO dead_letter (record_json, gfx_pc_id, file_path, retry_count, error_reason)
                VALUES (?, ?, ?, ?, ?)
            """, (row["record_json"], row["gfx_pc_id"], row["file_path"], row["retry_count"], error))
            await self._db.execute("DELETE FROM pending_sync WHERE id = ?", (queue_id,))
        else:
            # 재시도 카운트 증가
            await self._db.execute(
                "UPDATE pending_sync SET retry_count = retry_count + 1, last_error = ? WHERE id = ?",
                (error, queue_id)
            )
        await self._db.commit()
```

### 5.5 SupabaseClient (httpx)

```python
# src/sync_agent/db/supabase_client.py

import httpx

class RateLimitError(Exception):
    """Rate Limit 초과 예외."""
    pass

class SupabaseClient:
    """httpx 기반 Supabase REST 클라이언트."""

    def __init__(self, url: str, secret_key: str) -> None:
        self.url = url
        self.secret_key = secret_key
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """HTTP 클라이언트 초기화."""
        self._client = httpx.AsyncClient(
            base_url=f"{self.url}/rest/v1",
            headers={
                "apikey": self.secret_key,
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",
            },
            timeout=30.0,
        )

    async def upsert(
        self,
        table: str,
        records: list[dict],
        on_conflict: str = "gfx_pc_id,file_hash",
    ) -> UpsertResult:
        """Upsert 실행 (Rate Limit 예외 발생)."""
        response = await self._client.post(
            f"/{table}?on_conflict={on_conflict}",
            json=records,
        )

        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded")

        response.raise_for_status()
        return UpsertResult(success=True, count=len(records))

    async def close(self) -> None:
        """클라이언트 종료."""
        if self._client:
            await self._client.aclose()
```

---

## 6. 데이터베이스

### 6.1 Supabase 테이블

```sql
-- gfx_sessions 테이블
CREATE TABLE gfx_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gfx_pc_id TEXT NOT NULL,          -- PC 식별자
    session_id INTEGER NOT NULL,
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    raw_json JSONB NOT NULL,
    table_type TEXT,
    event_title TEXT,
    software_version TEXT,
    hand_count INTEGER DEFAULT 0,
    session_created_at TIMESTAMPTZ,
    sync_source TEXT DEFAULT 'nas_central',
    sync_status TEXT DEFAULT 'synced',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(gfx_pc_id, file_hash)      -- 복합 유니크 키
);

-- sync_events 테이블 (Realtime 활성화)
CREATE TABLE sync_events (
    id BIGSERIAL PRIMARY KEY,
    gfx_pc_id TEXT NOT NULL,
    event_type TEXT NOT NULL,         -- created, modified, error
    file_path TEXT,
    record_count INTEGER DEFAULT 1,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Realtime 활성화
ALTER PUBLICATION supabase_realtime ADD TABLE sync_events;

-- PC별 상태 뷰
CREATE VIEW pc_status AS
SELECT
    gfx_pc_id,
    COUNT(*) as total_files,
    MAX(created_at) as last_sync,
    COUNT(*) FILTER (WHERE sync_status = 'error') as error_count
FROM gfx_sessions
GROUP BY gfx_pc_id;
```

### 6.2 SQLite 스키마 (Offline Queue)

```sql
-- pending_sync 테이블
CREATE TABLE pending_sync (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_json TEXT NOT NULL,
    gfx_pc_id TEXT NOT NULL,
    file_path TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_error TEXT
);

-- dead_letter 테이블 (Dead Letter Queue)
CREATE TABLE dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_json TEXT NOT NULL,
    gfx_pc_id TEXT NOT NULL,
    file_path TEXT,
    retry_count INTEGER,
    error_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. 의존성

```toml
# pyproject.toml

[project]
dependencies = [
    "pydantic-settings>=2.0.0",   # 설정 관리
    "aiosqlite>=0.19.0",          # 비동기 SQLite
    "httpx>=0.27.0",              # HTTP 클라이언트
    "watchdog>=4.0.0",            # 폴링 감시
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
]
```

### 제거된 의존성

| 패키지 | 이유 |
|--------|------|
| `watchfiles` | SMB 미지원, 로컬 전용 |
| `supabase` | 무거움, httpx로 대체 |
| `pystray` | GUI 제거 |
| `Pillow` | GUI 제거 |

---

## 8. 모니터링

### 8.1 지표

| 지표 | 임계값 | 알림 |
|------|--------|------|
| 디스크 사용량 | 80% | 경고 |
| 메모리 사용량 | 512MB | 경고 |
| BatchQueue pending | 500 | 경고 |
| OfflineQueue pending | 5000 | 긴급 |
| retry_count >= 5 | 10건 | 검토 필요 |
| 연속 실패 | 5회 | 알림 |
| Dead Letter Queue | 1건 이상 | 검토 필요 |

### 8.2 헬스체크 엔드포인트

```json
GET /health

{
  "status": "healthy",
  "uptime_seconds": 3600,
  "components": {
    "watcher": "running",
    "supabase": "connected",
    "offline_queue": {
      "pending_count": 12,
      "dead_letter_count": 0
    },
    "batch_queue": {
      "pending_count": 45
    }
  },
  "last_sync": "2026-01-13T10:30:00Z",
  "watched_pcs": ["PC01", "PC02", "PC03"]
}
```

---

## 9. 배포

### 9.1 Docker Compose

```yaml
# docker-compose.yml

version: '3.8'

services:
  sync-agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
    volumes:
      - /volume1/gfx_data:/app/data:ro
      - sync_queue:/app/queue
    environment:
      GFX_SYNC_SUPABASE_URL: ${SUPABASE_URL}
      GFX_SYNC_SUPABASE_SECRET_KEY: ${SUPABASE_SECRET_KEY}
      GFX_SYNC_NAS_BASE_PATH: /app/data
      GFX_SYNC_POLL_INTERVAL: "2.0"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  dashboard:
    build:
      context: ./dashboard
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_SUPABASE_URL: ${SUPABASE_URL}
      NEXT_PUBLIC_SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY}
    depends_on:
      - sync-agent

volumes:
  sync_queue:
```

### 9.2 실행 방법

```bash
# 1. 환경 변수 설정
cp .env.example .env
# SUPABASE_URL, SUPABASE_SECRET_KEY 등 설정

# 2. Docker Compose 실행
docker-compose up -d

# 3. 로그 확인
docker-compose logs -f sync-agent

# 4. 대시보드 접속
# http://NAS-IP:3000
```

---

## 10. 구현 순서 (TDD)

### Phase 1: 인프라 계층
1. `config/settings.py` - 환경 변수 기반 단일 설정
2. `queue/offline_queue.py` - aiosqlite + Dead Letter Queue
3. `db/supabase_client.py` - httpx + Rate Limit 예외

### Phase 2: 핵심 로직
4. `core/json_parser.py` - 파싱 + 해시 생성
5. `queue/batch_queue.py` - 인메모리 배치 큐
6. `core/sync_service.py` - 지수 백오프 포함

### Phase 3: 감시자 계층
7. `watcher/registry.py` - PC 레지스트리 관리
8. `watcher/polling_watcher.py` - watchdog 폴링

### Phase 4: 오케스트레이션
9. `core/agent.py` - 시작 시 전체 스캔 포함
10. `main.py` - CLI, 시그널 핸들링

### Phase 5: 운영
11. `health/healthcheck.py` - 상세 헬스체크
12. Docker 설정 업데이트

---

---

## 11. Claude Code 자동화 워크플로우

> **목적**: Claude Code가 비밀번호 입력 없이 NAS 서버의 Docker 컨테이너를 자동으로 관리

### 11.1 자동화 아키텍처

```
┌────────────────────────────────────────────────────────────────────────┐
│                         Claude Code (Windows)                           │
│                                                                         │
│   /auto "작업 지시"                                                     │
│       │                                                                 │
│       ▼                                                                 │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  SSH 키 인증 (비밀번호 없음)                                     │  │
│   │  ssh aiden@221.149.191.204 "..."                                │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│       │                                                                 │
└───────┼─────────────────────────────────────────────────────────────────┘
        │ SSH + sudo NOPASSWD
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Synology NAS (221.149.191.204)                     │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  /volume1/docker/gfx-sync/                                      │  │
│   │  ├── src/sync_agent/core/   ← 코드 배포 경로                    │  │
│   │  ├── docker-compose.yml                                         │  │
│   │  └── .env                                                       │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│       │                                                                 │
│       ▼ docker-compose build && up -d                                  │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │  gfx-sync-agent (Docker Container)                               │  │
│   │  - SyncService + BatchQueue + OfflineQueue                      │  │
│   │  - SupabaseClient (httpx)                                       │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│       │                                                                 │
└───────┼─────────────────────────────────────────────────────────────────┘
        │ HTTPS
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          Supabase Cloud                                 │
│   gfx_sessions 테이블 (UNIQUE: session_id)                             │
└────────────────────────────────────────────────────────────────────────┘
```

### 11.2 자동화 설정 요약

| 설정 | 값 | 목적 |
|------|-----|------|
| **SSH 키 인증** | `~/.ssh/id_rsa.pub` → NAS `authorized_keys` | 비밀번호 없이 접속 |
| **PubkeyAuthentication** | `/etc/ssh/sshd_config` 활성화 | SSH 키 인증 허용 |
| **홈 디렉토리 권한** | `chmod 755 /volume1/homes/aiden` | Synology ACL 문제 해결 |
| **sudo NOPASSWD** | `/etc/sudoers.d/aiden` | Docker 명령 비밀번호 없이 실행 |

### 11.3 자동화 워크플로우 (코드 배포)

```bash
# 1. 로컬 파일을 NAS 임시 경로에 업로드
cat C:\claude\gfx_json\src\sync_agent\core\json_parser.py | \
  ssh aiden@221.149.191.204 "cat > /tmp/json_parser.py"

# 2. sudo로 프로젝트 경로에 복사
ssh aiden@221.149.191.204 "sudo cp /tmp/json_parser.py /volume1/docker/gfx-sync/src/sync_agent/core/"

# 3. Docker 이미지 재빌드 및 컨테이너 재시작
ssh aiden@221.149.191.204 "cd /volume1/docker/gfx-sync && \
  sudo /usr/local/bin/docker-compose down && \
  sudo /usr/local/bin/docker-compose build --no-cache && \
  sudo /usr/local/bin/docker-compose up -d"

# 4. 로그 확인으로 배포 검증
ssh aiden@221.149.191.204 "sudo /usr/local/bin/docker logs --tail 30 gfx-sync-agent"
```

### 11.4 주요 자동화 명령어

| 작업 | 명령어 |
|------|--------|
| **컨테이너 상태** | `ssh aiden@221.149.191.204 "sudo /usr/local/bin/docker ps --filter name=gfx"` |
| **로그 확인** | `ssh aiden@221.149.191.204 "sudo /usr/local/bin/docker logs --tail 50 gfx-sync-agent"` |
| **컨테이너 재시작** | `ssh aiden@221.149.191.204 "sudo /usr/local/bin/docker restart gfx-sync-agent"` |
| **빌드 + 시작** | `ssh aiden@221.149.191.204 "cd /volume1/docker/gfx-sync && sudo /usr/local/bin/docker-compose up -d --build"` |
| **전체 재빌드** | `ssh aiden@221.149.191.204 "cd /volume1/docker/gfx-sync && sudo /usr/local/bin/docker-compose build --no-cache"` |

### 11.5 NAS 서버 정보

| 항목 | 값 |
|------|-----|
| **외부 IP** | `221.149.191.204` |
| **내부 IP** | `10.10.100.122` |
| **DSM 웹** | `https://221.149.191.204:5001` |
| **SSH 사용자** | `aiden` |
| **프로젝트 경로** | `/volume1/docker/gfx-sync` |
| **Docker 경로** | `/usr/local/bin/docker` |
| **컨테이너 이름** | `gfx-sync-agent` |

### 11.6 자동화 트러블슈팅

| 오류 | 원인 | 해결 |
|------|------|------|
| `Permission denied (publickey)` | SSH 키 인증 실패 | `chmod 755 /volume1/homes/aiden` |
| `sudo: a password is required` | NOPASSWD 미설정 | `/etc/sudoers.d/aiden` 생성 |
| `PGRST204: column not found` | DB 스키마 불일치 | 코드 수정 후 재배포 |
| `docker: command not found` | PATH 미포함 | 전체 경로 사용 |
| SCP 실패 | Synology SCP 이슈 | SSH + cat 방식 사용 |

### 11.7 상세 설정 문서

자동화 설정의 상세 절차는 다음 문서 참조:
- **`docs/NAS-SSH-GUIDE.md`** → 섹션 8. Claude Code 자동화 설정

---

## 12. 변경 이력

| 버전 | 날짜 | 변경 내용 | 작성자 |
|------|------|----------|--------|
| 1.0 | 2026-01-13 | 초안 작성 | Claude |
| 1.1 | 2026-01-13 | watchfiles 기반으로 변경 | Claude |
| 2.0 | 2026-01-13 | NAS 중앙 + PC 로컬 이중 모드 | Claude |
| 3.0 | 2026-01-13 | NAS 전용 전면 재설계, 오류 분석 추가, Dead Letter Queue | Claude |
| **3.1** | **2026-01-16** | **Claude Code 자동화 워크플로우 섹션 추가, DB 스키마 수정 (session_id UNIQUE)** | **Claude** |
