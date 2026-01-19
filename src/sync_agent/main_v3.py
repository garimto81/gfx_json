"""SyncAgent v3.0 메인 진입점.

NAS 전용 동기화 에이전트.
"""

from __future__ import annotations

import sys
import os

# 즉시 출력 (버퍼링 없이)
print("[BOOT] main_v3.py 로드 시작", flush=True)
print(f"[BOOT] Python: {sys.version}", flush=True)
print(f"[BOOT] CWD: {os.getcwd()}", flush=True)
print(f"[BOOT] PYTHONPATH: {os.environ.get('PYTHONPATH', 'N/A')}", flush=True)

# 단계별 import (어디서 막히는지 확인)
print("[BOOT] import asyncio...", flush=True)
import asyncio

print("[BOOT] import logging...", flush=True)
import logging

print("[BOOT] import signal...", flush=True)
import signal

print("[BOOT] import pathlib...", flush=True)
from pathlib import Path

print("[BOOT] 기본 모듈 import 완료", flush=True)

logger = logging.getLogger(__name__)


def debug_startup() -> None:
    """시작 시 디버깅 정보 출력."""
    print("=" * 60)
    print("[DEBUG] GFX Sync Agent 시작 디버깅")
    print("=" * 60)

    # Python 정보
    print(f"[DEBUG] Python: {sys.version}")
    print(f"[DEBUG] 실행 경로: {os.getcwd()}")
    print(f"[DEBUG] PYTHONPATH: {os.environ.get('PYTHONPATH', '(미설정)')}")

    # 환경 변수 확인
    print("-" * 40)
    print("[DEBUG] 환경 변수:")
    env_vars = [
        "GFX_SYNC_SUPABASE_URL",
        "GFX_SYNC_SUPABASE_SECRET_KEY",
        "GFX_SYNC_NAS_BASE_PATH",
        "GFX_SYNC_HEALTH_PORT",
    ]
    for var in env_vars:
        value = os.environ.get(var, "(미설정)")
        # 민감 정보 마스킹
        if "SECRET" in var and value != "(미설정)":
            value = f"{value[:10]}...{value[-4:]}" if len(value) > 14 else "***"
        elif "URL" in var and value != "(미설정)":
            value = value[:40] + "..." if len(value) > 40 else value
        print(f"  {var}: {value}")

    # 경로 확인
    print("-" * 40)
    print("[DEBUG] 경로 확인:")
    paths_to_check = [
        "/app",
        "/app/src",
        "/app/src/sync_agent",
        "/app/data",
        "/app/data/config",
        "/app/data/PC01",
        "/app/queue",
    ]
    for path in paths_to_check:
        exists = Path(path).exists()
        is_dir = Path(path).is_dir() if exists else False
        status = "✓ 존재" if exists else "✗ 없음"
        if exists and is_dir:
            try:
                files = list(Path(path).iterdir())[:5]
                file_list = ", ".join(f.name for f in files)
                if len(list(Path(path).iterdir())) > 5:
                    file_list += "..."
                status += f" ({file_list})"
            except Exception:
                pass
        print(f"  {path}: {status}")

    print("=" * 60)
    sys.stdout.flush()


# 모듈 import 테스트 (단계별)
try:
    print("[BOOT] import Settings...", flush=True)
    from src.sync_agent.config.settings import Settings
    print("[BOOT] Settings import 완료", flush=True)

    print("[BOOT] import SyncAgent...", flush=True)
    from src.sync_agent.core.agent import SyncAgent
    print("[BOOT] SyncAgent import 완료", flush=True)

    print("[BOOT] import HealthCheckServer...", flush=True)
    from src.sync_agent.health.healthcheck import HealthCheckServer
    print("[BOOT] HealthCheckServer import 완료", flush=True)

    print("[BOOT] 모든 모듈 import 성공!", flush=True)
except ImportError as e:
    print(f"[ERROR] 모듈 import 실패: {e}", flush=True)
    print(f"[ERROR] sys.path: {sys.path}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] import 중 예외 발생: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)


def setup_logging(level: str = "INFO") -> None:
    """로깅 설정."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


async def main() -> None:
    """메인 함수."""
    print("[MAIN] main() 시작", flush=True)

    # 설정 로드
    print("[MAIN] Settings() 초기화 중...", flush=True)
    settings = Settings()
    print(f"[MAIN] Settings 로드 완료: nas_path={settings.nas_base_path}", flush=True)

    # 로깅 설정
    setup_logging(settings.log_level)

    logger.info("=" * 60)
    logger.info("GFX Sync Agent v3.0 - NAS 전용")
    logger.info("=" * 60)

    # 에이전트 초기화
    print("[MAIN] SyncAgent() 초기화 중...", flush=True)
    agent = SyncAgent(settings=settings)
    print("[MAIN] SyncAgent 초기화 완료", flush=True)

    # 헬스체크 서버 (선택)
    health_server: HealthCheckServer | None = None
    if settings.health_enabled:
        print(f"[MAIN] HealthCheckServer 시작 중 (포트: {settings.health_port})...", flush=True)
        health_server = HealthCheckServer(
            port=settings.health_port,
            stats_callback=agent.get_stats,
        )
        health_server.start()
        print("[MAIN] HealthCheckServer 시작 완료", flush=True)

    # 시그널 핸들러
    def handle_signal(sig: int, frame: object) -> None:
        logger.info(f"시그널 수신: {signal.Signals(sig).name}")
        asyncio.create_task(agent.stop())

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print("[MAIN] agent.start() 호출...", flush=True)
    try:
        await agent.start()
    except asyncio.CancelledError:
        logger.info("에이전트 취소됨")
    except Exception as e:
        print(f"[ERROR] agent.start() 오류: {e}", flush=True)
        logger.error(f"에이전트 오류: {e}")
        raise
    finally:
        if health_server:
            health_server.stop()
        await agent.stop()

    logger.info("GFX Sync Agent 종료")


def run() -> None:
    """진입점."""
    # 시작 시 디버깅 정보 출력
    debug_startup()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트")
    except Exception as e:
        print(f"[ERROR] 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run()
