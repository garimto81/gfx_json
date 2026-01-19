# Broadcast Module

Supabase Realtime 브로드캐스트 모듈.

## 개요

GFX 데이터 동기화 시 실시간 이벤트를 브로드캐스트하여 클라이언트에게 알림을 전송합니다.

### 주요 기능

- **핸드 삽입 이벤트**: 새로운 핸드가 `gfx_hands` 테이블에 INSERT됨
- **세션 업데이트**: 세션 상태(핸드 수, 상태 등) 변경
- **핸드 완료**: 핸드가 완료되고 승자가 결정됨
- **자동 재시도**: 지수 백오프를 사용한 재시도 로직
- **배치 브로드캐스트**: 여러 이벤트를 순차적으로 전송

## 파일 구조

```
broadcast/
├── __init__.py                  # 모듈 exports
├── realtime_publisher.py        # RealtimePublisher 구현
├── integration_example.py       # SyncService 통합 예제
└── README.md                    # 문서 (현재 파일)
```

## 사용 방법

### 1. 기본 사용

```python
import asyncio
from uuid import uuid4
from src.sync_agent.broadcast.realtime_publisher import RealtimePublisher

async def main():
    # Publisher 생성 및 연결
    publisher = RealtimePublisher(
        supabase_url="https://your-project.supabase.co",
        supabase_key="your_secret_key",
        channel="gfx_events",
    )
    await publisher.connect()

    # 핸드 삽입 이벤트 브로드캐스트
    await publisher.publish_hand_inserted(
        hand_id=uuid4(),
        session_id=123,
        hand_num=5,
        player_count=6,
        small_blind=10.0,
        big_blind=20.0,
    )

    # 연결 종료
    await publisher.disconnect()

asyncio.run(main())
```

### 2. Context Manager 사용

```python
async def main():
    async with RealtimePublisher(
        supabase_url="https://your-project.supabase.co",
        supabase_key="your_secret_key",
        channel="gfx_events",
    ) as publisher:
        # 세션 업데이트 이벤트
        await publisher.publish_session_updated(
            session_id=123,
            hand_count=10,
            status="active",
        )
    # 자동으로 연결 종료됨
```

### 3. SyncService와 통합

```python
from src.sync_agent.broadcast.integration_example import SyncServiceWithBroadcast
from src.sync_agent.db.supabase_client import SupabaseClient
from src.sync_agent.broadcast.realtime_publisher import RealtimePublisher

async def main():
    # SupabaseClient 생성
    client = SupabaseClient(
        url="https://your-project.supabase.co",
        secret_key="your_secret_key",
    )
    await client.connect()

    # RealtimePublisher 생성
    publisher = RealtimePublisher(
        supabase_url="https://your-project.supabase.co",
        supabase_key="your_secret_key",
        channel="gfx_events",
    )
    await publisher.connect()

    # SyncServiceWithBroadcast 생성
    service = SyncServiceWithBroadcast(
        client=client,
        publisher=publisher,
    )

    # 파일 동기화 (자동 브로드캐스트)
    result = await service.sync_file(
        file_path="/path/to/gfx_data.json",
        gfx_pc_id="PC01",
    )

    if result.success:
        print(f"✓ 동기화 및 브로드캐스트 완료: session_id={result.session_id}")

    # 연결 종료
    await publisher.disconnect()
    await client.close()

asyncio.run(main())
```

### 4. 배치 브로드캐스트

```python
from src.sync_agent.broadcast.realtime_publisher import (
    RealtimePublisher,
    BroadcastMessage,
    BroadcastEvent,
)
from uuid import uuid4

async def main():
    async with RealtimePublisher(...) as publisher:
        messages = [
            BroadcastMessage(
                event=BroadcastEvent.HAND_INSERTED,
                table="gfx_hands",
                payload={"hand_id": str(uuid4()), "session_id": 1},
            ),
            BroadcastMessage(
                event=BroadcastEvent.HAND_INSERTED,
                table="gfx_hands",
                payload={"hand_id": str(uuid4()), "session_id": 1},
            ),
        ]

        success_count = await publisher.publish_batch(messages)
        print(f"브로드캐스트 성공: {success_count}/{len(messages)}")

asyncio.run(main())
```

## API 레퍼런스

### RealtimePublisher

#### `__init__(supabase_url, supabase_key, channel="gfx_events", timeout=10.0, max_retries=3)`

RealtimePublisher 생성.

**Parameters:**
- `supabase_url` (str): Supabase 프로젝트 URL
- `supabase_key` (str): Supabase Secret Key (또는 Anon Key)
- `channel` (str): 브로드캐스트 채널명 (기본: "gfx_events")
- `timeout` (float): 요청 타임아웃 (초, 기본: 10.0)
- `max_retries` (int): 최대 재시도 횟수 (기본: 3)

#### `async connect()`

HTTP 클라이언트 초기화 및 연결.

#### `async disconnect()`

연결 종료.

#### `async publish_hand_inserted(hand_id, session_id, hand_num, player_count=0, small_blind=None, big_blind=None)`

핸드 삽입 이벤트 브로드캐스트.

**Parameters:**
- `hand_id` (UUID): 핸드 UUID
- `session_id` (int): 세션 ID
- `hand_num` (int): 핸드 번호
- `player_count` (int): 플레이어 수
- `small_blind` (float | None): 스몰 블라인드
- `big_blind` (float | None): 빅 블라인드

**Returns:** `bool` - 성공 여부

#### `async publish_session_updated(session_id, hand_count, status=None)`

세션 업데이트 이벤트 브로드캐스트.

**Parameters:**
- `session_id` (int): 세션 ID
- `hand_count` (int): 현재 핸드 수
- `status` (str | None): 세션 상태 (active, completed 등)

**Returns:** `bool` - 성공 여부

#### `async publish_hand_completed(hand_id, session_id, hand_num, winner_name=None, pot_size=None)`

핸드 완료 이벤트 브로드캐스트.

**Parameters:**
- `hand_id` (UUID): 핸드 UUID
- `session_id` (int): 세션 ID
- `hand_num` (int): 핸드 번호
- `winner_name` (str | None): 승자 이름
- `pot_size` (float | None): 최종 팟 크기

**Returns:** `bool` - 성공 여부

#### `async publish_batch(messages)`

배치 브로드캐스트.

**Parameters:**
- `messages` (list[BroadcastMessage]): 브로드캐스트할 메시지 리스트

**Returns:** `int` - 성공한 메시지 수

### BroadcastMessage

#### `__init__(event, table, payload, timestamp=None)`

브로드캐스트 메시지 생성.

**Parameters:**
- `event` (BroadcastEvent): 이벤트 타입
- `table` (str): 테이블명
- `payload` (dict): 데이터 페이로드
- `timestamp` (datetime | None): 이벤트 발생 시간 (기본: 현재 시간)

#### `to_dict()`

딕셔너리 변환.

**Returns:** `dict[str, Any]`

### BroadcastEvent (Enum)

이벤트 타입:
- `HAND_INSERTED`: 핸드 삽입
- `SESSION_UPDATED`: 세션 업데이트
- `HAND_COMPLETED`: 핸드 완료

## 에러 처리

### 재시도 로직

브로드캐스트 실패 시 지수 백오프를 사용한 재시도:

```
시도 1: 즉시 실행
시도 2: 2초 대기 후 (2^1)
시도 3: 4초 대기 후 (2^2)
실패 → False 반환
```

### 예외 처리

- `httpx.TimeoutException`: 타임아웃 발생 시 재시도
- `httpx.RequestError`: 요청 오류 시 재시도
- 기타 예외: False 반환 및 로그 기록

## 테스트

```bash
# 단위 테스트 실행
pytest tests/test_realtime_publisher.py -v

# 특정 테스트 실행
pytest tests/test_realtime_publisher.py::TestRealtimePublisher::test_connect_disconnect -v

# 커버리지 확인
pytest tests/test_realtime_publisher.py --cov=src.sync_agent.broadcast
```

## Supabase 설정

### 1. Realtime 활성화

Supabase Dashboard → Database → Replication:

```sql
-- Realtime 활성화 (REPLICA IDENTITY FULL)
ALTER TABLE json.gfx_hands REPLICA IDENTITY FULL;
ALTER TABLE json.gfx_sessions REPLICA IDENTITY FULL;
```

### 2. Broadcast RPC 함수 생성 (선택)

실제 WebSocket 브로드캐스트를 위한 RPC 함수:

```sql
CREATE OR REPLACE FUNCTION public.broadcast_event(
    channel_name TEXT,
    event_data JSONB
)
RETURNS VOID AS $$
BEGIN
    -- PostgreSQL NOTIFY 사용
    PERFORM pg_notify(channel_name, event_data::TEXT);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

### 3. 클라이언트 구독 (JavaScript 예제)

```javascript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY)

// 채널 구독
const channel = supabase.channel('gfx_events')
  .on('broadcast', { event: 'hand_inserted' }, (payload) => {
    console.log('새 핸드 삽입:', payload)
  })
  .on('broadcast', { event: 'session_updated' }, (payload) => {
    console.log('세션 업데이트:', payload)
  })
  .subscribe()
```

## 성능 고려사항

### 브로드캐스트 빈도

- 핸드 삽입: 즉시 브로드캐스트
- 세션 업데이트: 배치로 묶어서 전송 (예: 5초마다)
- 핸드 완료: 즉시 브로드캐스트

### 타임아웃 설정

```python
publisher = RealtimePublisher(
    supabase_url="...",
    supabase_key="...",
    timeout=10.0,  # 10초 타임아웃
    max_retries=3,  # 최대 3회 재시도
)
```

### 배치 처리

대량의 핸드를 동기화할 때는 배치 브로드캐스트 사용:

```python
messages = [
    BroadcastMessage(...) for hand in hands
]
success_count = await publisher.publish_batch(messages)
```

## 참고 문서

- [MODULE_1_2_DESIGN.md](../../../../automation_orchestration/docs/MODULE_1_2_DESIGN.md) - 전체 설계
- [Supabase Realtime Docs](https://supabase.com/docs/guides/realtime)
- [PostgreSQL NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html)

---

**최종 수정**: 2026-01-15
**작성자**: Python Developer Agent
