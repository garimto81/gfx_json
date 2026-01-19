# Synology NAS SSH 사용 가이드

## 문서 정보

| 항목 | 내용 |
|------|------|
| **버전** | 2.0 |
| **대상** | 일반 사용자 + Claude Code 자동화 |
| **작성일** | 2026-01-16 |
| **최종 수정** | 2026-01-16 (Claude Code 자동화 추가) |

---

## 1. SSH 접속 방법

### 1.1 GFX NAS 접속 정보

| 항목 | 값 |
|------|-----|
| **IP 주소** | `10.10.100.122` |
| **사용자** | `GGP` |
| **비밀번호** | `!@QW12qw` |
| **포트** | `22` (기본) |

### 1.2 Windows에서 SSH 접속

PowerShell 또는 명령 프롬프트를 열고:

```powershell
ssh GGP@10.10.100.122
```

비밀번호 입력 프롬프트가 나타나면 `!@QW12qw` 입력.

처음 접속 시 "fingerprint" 확인 메시지가 나타나면 `yes` 입력.

### 1.3 Synology DSM에서 SSH 활성화 (이미 활성화된 경우 생략)

1. **DSM 웹 접속**: 브라우저에서 `http://10.10.100.122:5000` 접속
2. **제어판** 열기
3. **터미널 및 SNMP** 클릭
4. **SSH 서비스 활성화** 체크
5. **적용** 클릭

### 1.4 접속 종료

```bash
exit
```

---

## 2. Docker 빌드 및 실행

### 2.1 프로젝트 폴더로 이동

```bash
cd /volume1/docker/gfx-sync
```

### 2.2 Docker 이미지 빌드 (소스 변경 후)

```bash
sudo docker-compose build
```

### 2.3 컨테이너 시작

```bash
sudo docker-compose up -d
```

### 2.4 빌드 + 시작 한번에

```bash
sudo docker-compose up -d --build
```

### 2.5 컨테이너 중지

```bash
sudo docker-compose down
```

### 2.6 전체 재빌드 (캐시 없이)

문제가 해결되지 않을 때:
```bash
sudo docker-compose down
sudo docker-compose build --no-cache
sudo docker-compose up -d
```

---

## 3. Docker 로그 확인 (핵심)

### 3.1 기본 로그 확인

전체 로그 출력 (오래된 로그부터):
```bash
sudo docker logs gfx-sync-agent
```

### 3.2 최근 로그만 확인 (권장)

최근 100줄만 보기:
```bash
sudo docker logs --tail 100 gfx-sync-agent
```

최근 50줄:
```bash
sudo docker logs --tail 50 gfx-sync-agent
```

### 3.3 실시간 로그 확인

로그를 실시간으로 계속 보기 (새 로그가 올라오면 자동 표시):
```bash
sudo docker logs -f gfx-sync-agent
```

실시간 + 최근 50줄부터 시작:
```bash
sudo docker logs -f --tail 50 gfx-sync-agent
```

**종료하려면**: `Ctrl + C`

### 3.4 시간 범위로 필터링

최근 1시간 로그:
```bash
sudo docker logs --since 1h gfx-sync-agent
```

최근 30분 로그:
```bash
sudo docker logs --since 30m gfx-sync-agent
```

최근 2시간 로그:
```bash
sudo docker logs --since 2h gfx-sync-agent
```

### 3.5 로그 메시지 해석

| 로그 메시지 | 의미 | 조치 |
|------------|------|------|
| `INFO - Starting SyncAgent` | 에이전트 시작됨 | 정상 |
| `INFO - File detected` | 새 JSON 파일 감지 | 정상 |
| `INFO - Synced to Supabase` | Supabase 동기화 성공 | 정상 |
| `WARNING - Connection retry` | 연결 재시도 중 | 잠시 대기 |
| `ERROR - Supabase connection failed` | Supabase 연결 실패 | 네트워크/API 키 확인 |
| `ERROR - Parse error` | JSON 파싱 오류 | 파일 형식 확인 |

---

## 4. 컨테이너 상태 확인

### 4.1 실행 중인 컨테이너 목록

```bash
sudo docker ps
```

**출력 예시**:
```
CONTAINER ID   IMAGE            STATUS          PORTS                    NAMES
a1b2c3d4e5f6   gfx-sync-agent   Up 2 hours      0.0.0.0:8081->8080/tcp   gfx-sync-agent
```

### 4.2 모든 컨테이너 (중지된 것 포함)

```bash
sudo docker ps -a
```

### 4.3 상태 값 의미

| STATUS | 의미 | 조치 |
|--------|------|------|
| `Up X hours` | 정상 실행 중 | 없음 |
| `Up X hours (healthy)` | 정상 + 헬스체크 통과 | 없음 |
| `Up X hours (unhealthy)` | 실행 중이나 문제 있음 | 로그 확인 |
| `Exited (0)` | 정상 종료됨 | 필요시 재시작 |
| `Exited (1)` | 오류로 종료됨 | 로그 확인 후 재시작 |
| `Restarting` | 재시작 중 | 잠시 대기 |

---

## 5. 간단한 트러블슈팅

### 5.1 컨테이너 재시작

문제가 있을 때 가장 먼저 시도:
```bash
sudo docker restart gfx-sync-agent
```

### 5.2 헬스체크

서비스가 정상인지 확인:
```bash
curl http://localhost:8080/health
```

**정상 응답**:
```json
{"status": "healthy"}
```

### 5.3 컨테이너 중지/시작

```bash
# 중지
sudo docker stop gfx-sync-agent

# 시작
sudo docker start gfx-sync-agent
```

### 5.4 자주 발생하는 문제

| 문제 | 증상 | 해결 방법 |
|------|------|----------|
| **컨테이너 중지됨** | `docker ps`에 안 보임 | `sudo docker start gfx-sync-agent` |
| **Supabase 연결 오류** | 로그에 `ConnectionError` | 네트워크 확인, `.env` API 키 확인 |
| **파일 감지 안 됨** | 로그에 새 파일 메시지 없음 | NAS 폴더 권한 확인 |
| **헬스체크 실패** | `curl` 응답 없음 | 컨테이너 재시작 |

---

## 6. 유용한 단축 명령어 모음

바로 복사해서 사용할 수 있는 명령어 목록:

```bash
# 컨테이너 상태 확인
sudo docker ps

# 최근 로그 100줄 확인
sudo docker logs --tail 100 gfx-sync-agent

# 실시간 로그 확인 (Ctrl+C로 종료)
sudo docker logs -f --tail 50 gfx-sync-agent

# 최근 1시간 로그
sudo docker logs --since 1h gfx-sync-agent

# 컨테이너 재시작
sudo docker restart gfx-sync-agent

# 헬스체크
curl http://localhost:8080/health

# SSH 종료
exit
```

---

## 7. GUI 대안 (SSH 없이)

SSH가 익숙하지 않다면 **Container Manager** 웹 UI 사용:

1. DSM 웹 접속
2. **Container Manager** 열기
3. **Container** → `gfx-sync-agent` 클릭
4. **Log** 탭에서 로그 확인

---

---

## 8. Claude Code 자동화 설정

> **목적**: Claude Code에서 비밀번호 입력 없이 NAS Docker 컨테이너를 자동으로 관리

### 8.1 사전 조건

| 항목 | 요구사항 |
|------|----------|
| **NAS** | SSH 서비스 활성화 + PubkeyAuthentication 활성화 |
| **Windows** | SSH 클라이언트 설치됨 (Windows 10+는 기본 제공) |
| **Claude Code** | 로컬 환경에서 SSH 명령 실행 가능 |

### 8.2 SSH 키 인증 설정

#### Step 1: SSH 키 생성 (Windows)

```powershell
# PowerShell에서 실행
# 키가 없는 경우만 생성
ssh-keygen -t ed25519 -C "claude-code@nas"
# 또는 기존 RSA 키 사용 가능
```

#### Step 2: 공개 키를 NAS에 등록

```bash
# bash에서 실행 (Git Bash 또는 WSL)
cat ~/.ssh/id_rsa.pub | ssh aiden@221.149.191.204 \
  "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

#### Step 3: NAS SSH 설정 수정 (비밀번호로 한 번 접속 필요)

```bash
# NAS SSH 접속
ssh aiden@221.149.191.204

# PubkeyAuthentication 활성화
sudo sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/#AuthorizedKeysFile/AuthorizedKeysFile/' /etc/ssh/sshd_config
```

#### Step 4: 홈 디렉토리 권한 수정 (Synology 필수)

```bash
# ACL 권한 문제 해결
sudo chmod 755 /volume1/homes/aiden
```

#### Step 5: 연결 테스트

```bash
# 비밀번호 없이 접속 확인
ssh -o BatchMode=yes aiden@221.149.191.204 "echo 'SSH 키 인증 성공'"
```

### 8.3 sudo NOPASSWD 설정

Docker 명령을 비밀번호 없이 실행하려면:

```bash
# NAS에서 실행
sudo bash -c 'echo "aiden ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/aiden'
sudo chmod 440 /etc/sudoers.d/aiden
```

> **보안 주의**: 필요한 명령만 허용하려면:
> ```
> aiden ALL=(ALL) NOPASSWD: /usr/local/bin/docker, /usr/local/bin/docker-compose
> ```

### 8.4 Claude Code 자동화 명령어

설정 완료 후 Claude Code에서 사용 가능한 명령어:

```bash
# 컨테이너 상태 확인
ssh aiden@221.149.191.204 "sudo /usr/local/bin/docker ps --filter name=gfx"

# 로그 확인
ssh aiden@221.149.191.204 "sudo /usr/local/bin/docker logs --tail 50 gfx-sync-agent"

# 컨테이너 재시작
ssh aiden@221.149.191.204 "sudo /usr/local/bin/docker restart gfx-sync-agent"

# Docker Compose 명령 (프로젝트 디렉토리)
ssh aiden@221.149.191.204 "cd /volume1/docker/gfx-sync && sudo /usr/local/bin/docker-compose up -d"
ssh aiden@221.149.191.204 "cd /volume1/docker/gfx-sync && sudo /usr/local/bin/docker-compose build --no-cache"
ssh aiden@221.149.191.204 "cd /volume1/docker/gfx-sync && sudo /usr/local/bin/docker-compose down"
```

### 8.5 코드 배포 자동화 (SSH + cat)

Synology NAS는 SCP가 안정적이지 않으므로 SSH + cat 방식 사용:

```bash
# 파일 업로드 (임시 경로)
cat local_file.py | ssh aiden@221.149.191.204 "cat > /tmp/file.py"

# 프로젝트 경로로 복사 (sudo 필요)
ssh aiden@221.149.191.204 "sudo cp /tmp/file.py /volume1/docker/gfx-sync/src/sync_agent/core/"

# 빌드 및 재시작
ssh aiden@221.149.191.204 "cd /volume1/docker/gfx-sync && sudo /usr/local/bin/docker-compose build --no-cache && sudo /usr/local/bin/docker-compose up -d"
```

### 8.6 설정 요약

| 항목 | 값 |
|------|-----|
| **NAS 외부 IP** | `221.149.191.204` |
| **NAS 내부 IP** | `10.10.100.122` |
| **사용자** | `aiden` |
| **프로젝트 경로** | `/volume1/docker/gfx-sync` |
| **Docker 경로** | `/usr/local/bin/docker` |
| **docker-compose 경로** | `/usr/local/bin/docker-compose` |

### 8.7 트러블슈팅

| 문제 | 원인 | 해결 |
|------|------|------|
| `Permission denied (publickey)` | ACL 권한 문제 | `chmod 755 /volume1/homes/aiden` |
| `sudo: a password is required` | NOPASSWD 미설정 | `/etc/sudoers.d/aiden` 생성 |
| `docker: command not found` | PATH 미포함 | 전체 경로 사용 `/usr/local/bin/docker` |
| SCP 실패 | Synology SCP 이슈 | SSH + cat 방식 사용 |

---

## 참조

| 문서 | 설명 |
|------|------|
| `docs/NAS-INSTALLATION-GUIDE.md` | NAS 설치 가이드 |
| `docs/DESIGN.md` | 시스템 설계 문서 |
| `docs/gfx_supabase_sync.md` | 시스템 PRD (자동화 워크플로우 포함) |
