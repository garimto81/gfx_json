# GFX Sync Agent v3.0 Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 의존성 설치 (README.md는 pyproject.toml에서 참조)
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

# 소스 코드 복사
COPY src/ src/

# 환경 변수
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV GFX_SYNC_NAS_BASE_PATH=/app/data
ENV GFX_SYNC_QUEUE_DB_PATH=/app/queue/pending.db

# 헬스체크 (python:3.12-slim에는 curl이 없으므로 Python 사용)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# 포트
EXPOSE 8080

# 실행 (디버깅용 - 단순 테스트)
CMD ["sh", "-c", "echo '[TEST] Container started' && python --version && ls -la /app && ls -la /app/src && python -u src/sync_agent/main_v3.py"]
