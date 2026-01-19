# GFX Sync Agent v3.0 - Synology NAS 설치 가이드

## 문서 정보

| 항목 | 내용 |
|------|------|
| **버전** | 3.0 |
| **대상** | Synology DSM 7.0+ |
| **작성일** | 2026-01-14 |

---

## 운영 환경

> **중요**: 이 프로젝트는 **GUI 기반 웹 인터페이스**로 NAS를 관리합니다.

### 접속 방식

```
┌─────────────────┐         ┌─────────────────────────────────────┐
│  Windows PC     │  HTTP   │  Synology NAS (DSM)                 │
│  웹 브라우저    │────────▶│  - File Station (파일 관리)         │
│                 │         │  - Container Manager (Docker 관리)  │
└─────────────────┘         └─────────────────────────────────────┘
```

### 작업 도구

| 작업 | 도구 | 접속 방법 |
|------|------|-----------|
| **파일 업로드/복사** | File Station | 웹 브라우저 → DSM → File Station |
| **Docker 빌드/실행** | Container Manager | 웹 브라우저 → DSM → Container Manager |
| **환경 변수 설정** | File Station | `.env` 파일 직접 편집 |
| **로그 확인** | Container Manager | Container → Log 탭 |

### SSH/CLI 미사용

- 모든 작업은 **웹 GUI**로 수행
- SSH 접속 불필요 (선택사항)
- 터미널 명령어는 트러블슈팅 참고용으로만 제공

---

## 1. 사전 요구사항

### 1.1 하드웨어
- Synology NAS (Docker 지원 모델)
- 권장: DS220+, DS720+, DS920+ 이상

### 1.2 소프트웨어
- DSM 7.0 이상
- Container Manager 패키지 (패키지 센터에서 설치)

### 1.3 외부 서비스
- Supabase 계정 및 프로젝트
- Supabase API 키 (Secret Key)

---

## 2. Synology NAS 설정

### 2.1 공유 폴더 생성

1. **Control Panel** → **Shared Folder** → **Create**
2. 설정:
   - **이름**: `gfx_data`
   - **설명**: GFX JSON 파일 저장소
   - **휴지통 활성화**: 선택 (권장)
3. 권한 설정:
   - GFX PC 사용자 계정에 **읽기/쓰기** 권한 부여

### 2.2 폴더 구조 생성

File Station에서 다음 폴더 구조를 생성합니다:

```
/volume1/gfx_data/
├── config/
│   └── pc_registry.json    # PC 등록 정보
├── PC01/                   # GFX PC 1 전용 (JSON 파일 직접 저장)
├── PC02/                   # GFX PC 2 전용
├── PC03/                   # GFX PC 3 전용 (필요시 추가)
└── _error/                 # 파싱 실패 파일 격리
```

### 2.3 pc_registry.json 생성

`/volume1/gfx_data/config/pc_registry.json` 파일을 생성합니다:

```json
{
  "pcs": [
    {
      "id": "PC01",
      "name": "GFX PC 1",
      "description": "1번 테이블",
      "path": "PC01"
    },
    {
      "id": "PC02",
      "name": "GFX PC 2",
      "description": "2번 테이블",
      "path": "PC02"
    }
  ]
}
```

### 2.4 SMB 서비스 확인

1. **Control Panel** → **File Services** → **SMB**
2. **Enable SMB service** 체크 확인
3. 최소 SMB 버전: SMB2 이상 권장

---

## 3. Container Manager 설정

### 3.1 프로젝트 파일 업로드

1. File Station에서 `/volume1/docker/gfx-sync/` 폴더 생성
2. 다음 파일들을 업로드:
   - `docker-compose.yml`
   - `Dockerfile`
   - `pyproject.toml`
   - `src/` 폴더 전체

### 3.2 환경 변수 파일 생성

`/volume1/docker/gfx-sync/.env` 파일을 생성합니다:

```env
# ===========================================
# Supabase 설정 (필수)
# ===========================================
# Supabase 프로젝트 URL
SUPABASE_URL=https://your-project.supabase.co

# Secret Key (서버사이드용)
# Supabase Dashboard > Settings > API Keys > Secret key
SUPABASE_SECRET_KEY=sb_secret_xxxxxxxxxxxxx

# Publishable Key (대시보드용)
SUPABASE_PUBLISHABLE_KEY=sb_publishable_xxxxxxxxxxxxx

# ===========================================
# NAS 설정 (필수)
# ===========================================
# GFX 데이터 폴더 경로 (절대 경로)
NAS_MOUNT_PATH=/volume1/gfx_data

# ===========================================
# Sync Agent 설정 (선택)
# ===========================================
# 폴링 주기 (초) - 기본값: 2.0
POLL_INTERVAL=2.0

# 배치 처리 크기 - 기본값: 500
BATCH_SIZE=500

# 배치 플러시 간격 (초) - 기본값: 5.0
FLUSH_INTERVAL=5.0

# 로그 레벨 - 기본값: INFO
LOG_LEVEL=INFO

# ===========================================
# Dashboard 설정 (선택)
# ===========================================
# 대시보드 포트 - 기본값: 3000
DASHBOARD_PORT=3000
```

### 3.3 docker-compose.yml 수정 (Synology용)

Synology의 볼륨 경로에 맞게 수정합니다:

```yaml
services:
  sync-agent:
    # ... 기존 설정 ...
    volumes:
      # Synology NAS 볼륨 경로로 수정
      - /volume1/gfx_data:/app/data:ro
      - sync_queue:/app/queue
```

### 3.4 Container Manager에서 프로젝트 생성

1. **Container Manager** 열기
2. **Project** → **Create**
3. 설정:
   - **Project name**: `gfx-sync`
   - **Path**: `/volume1/docker/gfx-sync`
   - **Source**: `docker-compose.yml`
4. **Build** 클릭하여 이미지 빌드
5. **Start** 클릭하여 서비스 시작

---

## 4. Supabase 설정

### 4.1 마이그레이션 실행

1. Supabase Dashboard 접속
2. **SQL Editor** 열기
3. `migrations/001_nas_central.sql` 내용 복사하여 실행
4. **Run** 클릭

### 4.2 생성 확인

다음 테이블과 뷰가 생성되었는지 확인:

**테이블**:
- `gfx_sessions` - PC별 세션 데이터
- `sync_events` - 동기화 이벤트 로그

**뷰**:
- `pc_status` - PC별 상태 집계
- `sync_stats` - 전체 통계
- `error_summary` - 오류 요약

검증 쿼리:
```sql
SELECT * FROM pc_status;
SELECT * FROM sync_stats;
```

---

## 5. 서비스 검증

### 5.1 컨테이너 상태 확인

Container Manager에서:
- `gfx-sync-agent`: **Running** 상태
- `gfx-dashboard`: **Running** 상태 (선택)

### 5.2 헬스체크

브라우저에서 접속:
```
http://<NAS-IP>:8081/health
```

> **참고**: 포트 8080은 Synology 서비스와 충돌할 수 있어 8081 사용

정상 응답:
```json
{"status": "healthy"}
```

### 5.3 대시보드 접속 (선택)

```
http://<NAS-IP>:3000
```

### 5.4 로그 확인

Container Manager → Container → `gfx-sync-agent` → **Log** 탭

또는 SSH로 접속하여:
```bash
docker logs gfx-sync-agent -f --tail 100
```

---

## 6. GFX PC 설정

### 6.1 네트워크 드라이브 연결

1. Windows 탐색기 열기
2. **네트워크 드라이브 연결** 클릭
3. 설정:
   - **드라이브 문자**: `Z:` (예시)
   - **폴더**: `\\<NAS-IP>\gfx_data\PC01`
   - **로그인 시 다시 연결** 체크
4. NAS 사용자 계정으로 로그인

### 6.2 PokerGFX 출력 경로 설정

PokerGFX 설정에서 JSON 출력 경로를 네트워크 드라이브로 변경:

```
Z:\
```

### 6.3 연결 테스트

1. PokerGFX에서 테스트 핸드 생성
2. NAS 폴더에 JSON 파일 생성 확인
3. Supabase에 데이터 동기화 확인

---

## 7. 운영 가이드

### 7.1 서비스 관리

| 작업 | Container Manager |
|------|-------------------|
| **시작** | Project → gfx-sync → Start |
| **중지** | Project → gfx-sync → Stop |
| **재시작** | Project → gfx-sync → Restart |
| **로그** | Container → gfx-sync-agent → Log |

### 7.2 자동 시작 설정

Container Manager에서 프로젝트 설정:
- **Auto-start**: 활성화
- NAS 재부팅 시 자동으로 서비스 시작

### 7.3 백업 권장 사항

| 대상 | 백업 주기 | 방법 |
|------|----------|------|
| `.env` 파일 | 변경 시 | 수동 복사 |
| `pc_registry.json` | 변경 시 | 수동 복사 |
| 오프라인 큐 DB | 주 1회 | Hyper Backup |
| Supabase 데이터 | 자동 | Supabase 자동 백업 |

---

## 8. 트러블슈팅

### 8.1 Supabase 연결 오류

**증상**: 로그에 `ConnectionError` 또는 `401 Unauthorized`

**해결**:
1. `.env` 파일의 `SUPABASE_URL` 확인
2. `SUPABASE_SECRET_KEY` 값 확인 (sb_secret_ 접두사)
3. Supabase 대시보드에서 API 키 재발급

### 8.2 SMB 권한 오류

**증상**: 파일 읽기 실패, `Permission denied`

**해결**:
1. 공유 폴더 권한 확인
2. SMB 사용자 권한 확인
3. docker-compose.yml의 볼륨 마운트 경로 확인

### 8.3 동기화 지연

**증상**: 파일 생성 후 동기화까지 오래 걸림

**해결**:
1. `POLL_INTERVAL` 값 확인 (기본 2초)
2. NAS CPU/메모리 사용률 확인
3. 네트워크 상태 확인

### 8.4 오프라인 큐 적체

**증상**: 동기화 실패 건수 증가

**해결**:
1. Supabase 연결 상태 확인
2. 로그에서 오류 메시지 확인
3. 필요시 서비스 재시작

### 8.5 컨테이너 시작 실패

**증상**: 컨테이너가 바로 종료됨

**해결**:
1. 로그 확인: `docker logs gfx-sync-agent`
2. `.env` 파일 문법 오류 확인
3. 볼륨 마운트 경로 확인

### 8.6 포트 충돌 오류 (external connectivity)

**증상**:
```
Error response from daemon: driver failed programming external connectivity on endpoint gfx-sync-agent
Exit Code: 1
```

**원인**: Synology 서비스(Web Station, Photos 등)가 포트 8080을 이미 사용 중

**해결 (GUI)**:

1. **Container Manager** → **Project** → `gfx-sync` → **Stop**
2. **File Station**에서 `docker-compose.yml` 편집:
   ```yaml
   ports:
     - "8081:8080"  # 8080 → 8081로 변경
   ```
3. **Container Manager** → **Project** → `gfx-sync` → **Build** → **Start**

**포트 확인 (선택 - SSH)**:
```bash
sudo netstat -tlnp | grep :8080
```

### 8.7 볼륨 경로 인식 오류

**증상**: Container Manager가 `/volume/docker/...`로 경로를 잘못 인식

**원인**: docker-compose.yml에 경로를 하드코딩하면 Container Manager가 상대 경로로 해석

**해결**:
1. `.env` 파일에 `NAS_MOUNT_PATH=/volume1/gfx_data` 설정
2. docker-compose.yml에서 `${NAS_MOUNT_PATH}` 환경변수 사용
3. **Container Manager** → **Project** → **Rebuild**

---

## 9. 유용한 명령어

SSH 접속 후 사용 가능한 명령어:

```bash
# 컨테이너 상태 확인
docker ps -a

# 실시간 로그 확인
docker logs gfx-sync-agent -f

# 컨테이너 재시작
docker restart gfx-sync-agent

# 헬스체크
curl http://localhost:8080/health

# 오프라인 큐 확인 (컨테이너 내부)
docker exec gfx-sync-agent ls -la /app/queue/
```

---

## 10. 참조

| 문서 | 설명 |
|------|------|
| `docs/NAS-SSH-GUIDE.md` | **SSH 접속 및 로그 확인 가이드** |
| `docs/gfx_supabase_sync.md` | 시스템 PRD (전체 아키텍처) |
| `docs/DESIGN.md` | 기술 설계 문서 |
| `migrations/001_nas_central.sql` | DB 마이그레이션 스크립트 |
| `docs/checklists/NAS-REDESIGN.md` | 개발 진행 체크리스트 |
