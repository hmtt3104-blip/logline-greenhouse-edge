from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import monotonic
from typing import Any, Callable
from urllib.parse import urlparse

from .performance import duration_ms, get_performance_logger


LOGGER = logging.getLogger("greenhouse_bridge.direct_http")
PERF_LOGGER = get_performance_logger()


class DirectCommandHttpServer:
    """Tiny HTTP endpoint for direct encrypted app -> Raspberry command delivery."""

    def __init__(
        self,
        host: str,
        port: int,
        handle_packet: Callable[[str], dict[str, Any]],
    ) -> None:
        self.host = host
        self.port = port
        self._handle_packet = handle_packet
        self._server: _BridgeHttpServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        server = _BridgeHttpServer((self.host, self.port), _BridgeHttpHandler)
        server.packet_handler = self._handle_packet
        thread = Thread(
            target=server.serve_forever,
            name="greenhouse-bridge-direct-http",
            daemon=True,
        )
        thread.start()
        self._server = server
        self._thread = thread
        LOGGER.info("Direct command HTTP endpoint listening on %s:%s", self.host, self.port)

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=2.0)


class _BridgeHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    packet_handler: Callable[[str], dict[str, Any]]


class _BridgeHttpHandler(BaseHTTPRequestHandler):
    server_version = "GreenhouseBridgeDirect/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/health":
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "service": "greenhouse-bridge-direct-http",
                "status": "ready",
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        started_at = monotonic()
        parsed = urlparse(self.path)
        content_length_header = self.headers.get("Content-Length", "0").strip() or "0"
        content_length = None
        try:
            content_length = int(content_length_header)
        except ValueError:
            content_length = None
        if parsed.path != "/api/command":
            PERF_LOGGER.log_event(
                "direct_command_http",
                path=parsed.path,
                duration_ms=duration_ms(started_at),
                request_size_bytes=content_length,
                status="NOT_FOUND",
            )
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return

        try:
            packet = self._extract_packet()
        except ValueError as exc:
            PERF_LOGGER.log_event(
                "direct_command_http",
                path=parsed.path,
                duration_ms=duration_ms(started_at),
                request_size_bytes=content_length,
                status="INVALID_REQUEST",
                error=str(exc),
            )
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "status": "invalid_request", "detail": str(exc)},
            )
            return

        try:
            result = self.server.packet_handler(packet)
        except Exception as exc:  # pragma: no cover - last-resort protection
            LOGGER.exception("Direct command handler crashed")
            PERF_LOGGER.log_event(
                "direct_command_http",
                path=parsed.path,
                duration_ms=duration_ms(started_at),
                request_size_bytes=content_length,
                status="BRIDGE_ERROR",
                error=str(exc),
            )
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "status": "bridge_error", "detail": str(exc)},
            )
            return

        raw_status = result.get("http_status")
        status_code = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
        if raw_status is not None:
            try:
                status_code = HTTPStatus(int(raw_status))
            except (ValueError, TypeError):
                status_code = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
        PERF_LOGGER.log_event(
            "direct_command_http",
            path=parsed.path,
            duration_ms=duration_ms(started_at),
            request_size_bytes=content_length,
            status=result.get("status") or ("OK" if result.get("ok") else "FAILED"),
            ok=result.get("ok"),
            request_id=result.get("cmd_id"),
            target=result.get("target"),
            command=result.get("action"),
        )
        self._write_json(status_code, result)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        LOGGER.debug("%s - %s", self.address_string(), format % args)

    def _extract_packet(self) -> str:
        raw_length = self.headers.get("Content-Length", "0").strip() or "0"
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise ValueError(f"Invalid Content-Length: {raw_length}") from exc

        if content_length <= 0:
            raise ValueError("Missing request body")
        if content_length > 65536:
            raise ValueError("Request body too large")

        text = self.rfile.read(content_length).decode("utf-8", errors="replace").strip()
        if not text:
            raise ValueError("Empty request body")

        if text.startswith("{"):
            body = json.loads(text)
            packet = str(body.get("packet", "")).strip()
            if not packet:
                raise ValueError("JSON body must contain a non-empty packet")
            return packet

        return text

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)
