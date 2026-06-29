from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from greenhouse_bridge.config import BridgeConfig
from greenhouse_bridge.controller_http import HttpController
from greenhouse_bridge.models import CommandRequest
from greenhouse_bridge.state_store import StateStore


PREFIX = "GREENHOUSE_BRIDGE_"


class _ControlHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.__class__.requests.append(
            {
                "path": self.path,
                "body": body.decode("utf-8"),
                "host": self.headers.get("Host"),
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def local_control_server() -> str:
    _ControlHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), _ControlHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _load_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith(PREFIX):
            monkeypatch.delenv(key, raising=False)

    env_example = Path(__file__).resolve().parents[1] / ".env.example"
    for line in env_example.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.startswith(PREFIX):
            monkeypatch.setenv(key, value)


def test_no_hardware_synthetic_telemetry_and_local_command_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    local_control_server: str,
) -> None:
    _load_env_example(monkeypatch)

    config = BridgeConfig.from_env()

    assert config.dry_run is True
    assert config.firebase_enabled is False
    assert config.command_polling_enabled is False
    assert config.legacy_command_ingress_enabled is False
    assert config.telegram_egress_enabled is False
    assert config.telegram_bot_token == ""
    assert config.app_to_pi_key_b64 == ""

    state_store = StateStore()
    assert state_store.update_from_topic(
        "greenhouse/example/telemetry/greenhouse2/router_url",
        local_control_server,
    )
    assert state_store.update_from_topic("greenhouse/example/telemetry/greenhouse2/temp", "24.7")
    assert state_store.update_from_topic("greenhouse/example/telemetry/greenhouse2/humidity", "58.2")
    assert state_store.update_from_topic("greenhouse/example/telemetry/greenhouse2/state", "IDLE")

    snapshot = state_store.next_snapshot("2026-06-29T00:00:00Z")
    assert snapshot.g2.router_url == local_control_server
    assert snapshot.g2.temp == 24.7
    assert snapshot.g2.humidity == 58.2
    assert snapshot.g2.state == "IDLE"

    controller = HttpController(config=config, state_store=state_store)
    receipt = controller.dispatch(
        CommandRequest(
            cmd_id="synthetic-stop",
            seq=1,
            ts="2026-06-29T00:00:00Z",
            ttl_sec=60,
            target="g2",
            action="stop",
        )
    )

    assert receipt.http_status == 200
    assert receipt.firmware_cmd == "stop"
    assert receipt.target_url == f"{local_control_server}/control"
    assert "greenhouse-device" not in receipt.target_url
    assert _ControlHandler.requests == [
        {
            "path": "/control",
            "body": "cmd=stop",
            "host": local_control_server.removeprefix("http://"),
        }
    ]
