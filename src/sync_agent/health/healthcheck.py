"""Docker 헬스체크 HTTP 서버.

간단한 HTTP 서버로 컨테이너 상태 제공.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """헬스체크 HTTP 핸들러."""

    stats_callback: Callable[[], dict[str, Any]] | None = None

    def do_GET(self) -> None:
        """GET 요청 처리."""
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/ready":
            self._handle_ready()
        elif self.path == "/stats":
            self._handle_stats()
        else:
            self._send_response(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _handle_health(self) -> None:
        """헬스체크 엔드포인트."""
        response = {
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if self.stats_callback:
            try:
                stats = self.stats_callback()
                response["components"] = {
                    "watcher": "running" if stats.get("running") else "stopped",
                    "offline_queue": stats.get("offline_queue", {}),
                    "batch_queue": stats.get("batch_queue", {}),
                }
                response["watched_pcs"] = stats.get("registry", {}).get("pcs", [])
            except Exception as e:
                logger.warning(f"통계 조회 오류: {e}")

        self._send_response(HTTPStatus.OK, response)

    def _handle_ready(self) -> None:
        """준비 상태 엔드포인트."""
        # 기본적으로 healthy면 ready
        self._send_response(HTTPStatus.OK, {"ready": True})

    def _handle_stats(self) -> None:
        """상세 통계 엔드포인트."""
        if self.stats_callback:
            try:
                stats = self.stats_callback()
                self._send_response(HTTPStatus.OK, stats)
            except Exception as e:
                self._send_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})
        else:
            self._send_response(HTTPStatus.OK, {"message": "No stats available"})

    def _send_response(self, status: HTTPStatus, data: dict[str, Any]) -> None:
        """JSON 응답 전송."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        """로그 메시지 (디버그 레벨)."""
        logger.debug(f"HealthCheck: {args[0]}")


class HealthCheckServer:
    """헬스체크 HTTP 서버.

    Docker 컨테이너 헬스체크를 위한 간단한 HTTP 서버.

    Endpoints:
    - GET /health: 헬스체크 (status: healthy/unhealthy)
    - GET /ready: 준비 상태 (ready: true/false)
    - GET /stats: 상세 통계

    Examples:
        ```python
        def get_stats():
            return {"running": True, "files": 100}

        server = HealthCheckServer(port=8080, stats_callback=get_stats)
        server.start()

        # 종료
        server.stop()
        ```
    """

    def __init__(
        self,
        port: int = 8080,
        host: str = "0.0.0.0",
        stats_callback: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        """초기화.

        Args:
            port: 포트
            host: 호스트
            stats_callback: 통계 조회 콜백
        """
        self.port = port
        self.host = host
        self._stats_callback = stats_callback
        self._server: HTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        """서버 시작 (백그라운드 스레드)."""
        HealthCheckHandler.stats_callback = self._stats_callback

        self._server = HTTPServer((self.host, self.port), HealthCheckHandler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        logger.info(f"HealthCheck 서버 시작: http://{self.host}:{self.port}")

    def stop(self) -> None:
        """서버 중지."""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        logger.info("HealthCheck 서버 중지")

    @property
    def is_running(self) -> bool:
        """실행 중 여부."""
        return self._thread is not None and self._thread.is_alive()
