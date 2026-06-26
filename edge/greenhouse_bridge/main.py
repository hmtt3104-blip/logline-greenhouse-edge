from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from time import monotonic, sleep
from threading import Event, Lock, Thread
from typing import Any

from .command_guard import CommandGuard
from .config import BridgeConfig
from .controller_http import HttpController
from .crypto import CryptoBox
from .device_config_http import DeviceConfigHttpClient
from .direct_command_http import DirectCommandHttpServer
from .firebase_sync import FirebaseSync
from .greenhouse1_http import Greenhouse1HttpClient
from .models import CommandRequest
from .mqtt_bridge import MqttBridge
from .performance import duration_ms, get_performance_logger
from .state_store import StateStore
from .temperature_node_http import TemperatureNodeHttpClient
from .telegram_transport import TelegramTransport


LOGGER = logging.getLogger("greenhouse_bridge")


class GreenhouseBridgeApp:
    """Process composition root for the Raspberry bridge."""

    IMPORTANT_MQTT_CHANGE_TOPICS: tuple[str, ...] = (
        "greenhouse/example/telemetry/greenhouse2/state",
        "greenhouse/example/telemetry/greenhouse2/mode",
        "greenhouse/example/telemetry/greenhouse2/last_action",
        "greenhouse/example/telemetry/greenhouse2/level",
        "greenhouse/example/telemetry/greenhouse2/close_threshold",
        "greenhouse/example/events/greenhouse2",
    )

    def __init__(
        self,
        config: BridgeConfig,
        state_store: StateStore,
        mqtt_bridge: MqttBridge,
        controller_http: HttpController,
        crypto: CryptoBox,
        telegram: TelegramTransport,
        guard: CommandGuard,
        greenhouse1_http: Greenhouse1HttpClient | None = None,
        temperature_node_http: TemperatureNodeHttpClient | None = None,
        device_config_http: DeviceConfigHttpClient | None = None,
        direct_command_http: DirectCommandHttpServer | None = None,
        firebase_sync: FirebaseSync | None = None,
    ) -> None:
        self.config = config
        self.state_store = state_store
        self.mqtt_bridge = mqtt_bridge
        self.controller_http = controller_http
        self.crypto = crypto
        self.telegram = telegram
        self.guard = guard
        self.greenhouse1_http = greenhouse1_http
        self.temperature_node_http = temperature_node_http
        self.device_config_http = device_config_http
        self.direct_command_http = direct_command_http
        self.firebase_sync = firebase_sync
        self.perf_logger = get_performance_logger()
        self._runtime_lock = Lock()
        self._stop_event = Event()
        self._last_reactive_snapshot_at = 0.0

    def run(self) -> None:
        """Runtime loop for Raspberry bridge."""
        LOGGER.info("Starting greenhouse bridge")
        self.mqtt_bridge.start_telemetry_subscription()
        if self.direct_command_http is not None:
            self.direct_command_http.start()
        self._start_greenhouse1_status_worker()
        self._start_firebase_command_worker()
        next_snapshot_at = monotonic()
        expedited_snapshot_at: float | None = None
        command_polling_enabled = (
            self.config.command_polling_enabled
            and self.config.legacy_command_ingress_enabled
        )

        try:
            while True:
                now = monotonic()
                snapshot_due = now >= next_snapshot_at or (
                    expedited_snapshot_at is not None and now >= expedited_snapshot_at
                )
                if snapshot_due:
                    reason = "post_command" if (
                        expedited_snapshot_at is not None and now >= expedited_snapshot_at
                    ) else "periodic"
                    self._send_snapshot(reason=reason)
                    next_snapshot_at = now + self.config.telemetry_period_sec
                    expedited_snapshot_at = None

                next_wake_at = min(
                    next_snapshot_at,
                    expedited_snapshot_at if expedited_snapshot_at is not None else next_snapshot_at,
                )
                poll_timeout = max(
                    1,
                    min(
                        self.config.telegram_poll_timeout_sec,
                        int(
                            max(
                                1.0,
                                next_wake_at - monotonic(),
                            )
                        ),
                    ),
                )

                packets: list[str] = []
                if command_polling_enabled:
                    try:
                        packets = self.telegram.poll_packets(timeout_sec=poll_timeout)
                    except RuntimeError as exc:
                        if "HTTPError 409" in str(exc):
                            command_polling_enabled = False
                            LOGGER.warning(
                                "Telegram command polling disabled after 409 conflict; "
                                "continuing in telemetry-only mode until restart."
                            )
                        else:
                            raise

                for packet in packets:
                    if self.handle_command_packet(packet).get("ok"):
                        scheduled_at = monotonic() + self.config.post_command_snapshot_delay_sec
                        expedited_snapshot_at = (
                            scheduled_at
                            if expedited_snapshot_at is None
                            else min(expedited_snapshot_at, scheduled_at)
                        )

                if not packets:
                    sleep(self.config.loop_idle_sleep_sec)
        finally:
            self._stop_event.set()
            if self.direct_command_http is not None:
                self.direct_command_http.stop()
            self.mqtt_bridge.stop()

    def _start_firebase_command_worker(self) -> None:
        if self.firebase_sync is None or not self.firebase_sync.enabled:
            return

        thread = Thread(
            target=self._firebase_command_worker,
            name="greenhouse-bridge-firebase-commands",
            daemon=True,
        )
        thread.start()

    def _start_greenhouse1_status_worker(self) -> None:
        if self.greenhouse1_http is None or not self.greenhouse1_http.enabled:
            return

        thread = Thread(
            target=self._greenhouse1_status_worker,
            name="greenhouse-bridge-g1-status",
            daemon=True,
        )
        thread.start()

    def _firebase_command_worker(self) -> None:
        poll_interval = max(0.25, float(self.config.firebase_poll_interval_sec))
        while not self._stop_event.is_set():
            try:
                self._process_firebase_commands("g1")
                self._process_firebase_commands("g2")
            except Exception:
                LOGGER.exception("Failed to process Firebase commands")
            self._stop_event.wait(poll_interval)

    def _greenhouse1_status_worker(self) -> None:
        poll_interval = max(2.0, float(self.config.greenhouse1_status_poll_interval_sec))
        while not self._stop_event.is_set():
            try:
                self._refresh_greenhouse1_http_state()
            except Exception:
                LOGGER.exception("Failed to refresh Greenhouse 1 state via ESP32 /status")
            self._stop_event.wait(poll_interval)

    def _send_snapshot(self, reason: str = "periodic") -> None:
        started_at = monotonic()
        refreshed_g1 = None
        if self.greenhouse1_http is not None and self.greenhouse1_http.enabled:
            try:
                refreshed_g1 = self.greenhouse1_http.refresh(
                    previous=self.state_store.g1,
                    now_iso=self._now_iso(),
                )
            except Exception:
                LOGGER.exception("Failed to refresh Greenhouse 1 snapshot before telemetry send")
        refreshed = None
        if self.temperature_node_http is not None and self.temperature_node_http.enabled:
            refreshed = self.temperature_node_http.refresh(
                previous=self.state_store.t3,
                now_iso=self._now_iso(),
                excluded_urls=(
                    self.state_store.g1.router_url,
                    self.state_store.g2.router_url,
                ),
            )
        with self._runtime_lock:
            if refreshed_g1 is not None:
                self.state_store.replace_greenhouse1(refreshed_g1)
            if refreshed is not None:
                self.state_store.replace_temperature_node(refreshed)
            snapshot = self.state_store.next_snapshot(self._now_iso())
            packet = self.crypto.seal_telemetry(snapshot)
        if self.config.telegram_egress_enabled:
            try:
                self.telegram.send_packet(packet)
            except Exception:
                LOGGER.exception(
                    "Failed to send telemetry packet to Telegram; continuing with local/Firebase sync"
                )
        if self.firebase_sync is not None:
            try:
                self.firebase_sync.publish_g1_snapshot(snapshot, reason=reason)
                self.firebase_sync.publish_g2_snapshot(snapshot, reason=reason)
                self.firebase_sync.publish_t3_snapshot(snapshot, reason=reason)
            except Exception:  # pragma: no cover - depends on live Firebase/runtime state
                LOGGER.exception("Failed to publish greenhouse snapshot to Firebase")
        self.perf_logger.log_event(
            "telemetry_snapshot",
            reason=reason,
            seq=snapshot.seq,
            duration_ms=duration_ms(started_at),
            packet_size_bytes=len(packet.encode("utf-8")),
            alerts_count=len(snapshot.alerts),
            g1_status=snapshot.g1.router_status,
            g2_status=snapshot.g2.router_status,
            t3_status=snapshot.temperature_node.router_status,
            status="OK",
        )
        LOGGER.info("Sent telemetry snapshot seq=%s reason=%s", snapshot.seq, reason)

    def handle_mqtt_update(self, topic: str, retained: bool) -> None:
        if retained or topic not in self.IMPORTANT_MQTT_CHANGE_TOPICS:
            return

        now = monotonic()
        with self._runtime_lock:
            if now - self._last_reactive_snapshot_at < 1.0:
                return
            self._last_reactive_snapshot_at = now

        self._start_background_snapshot(reason="telemetry_change")

    def handle_command_packet(self, packet: str) -> dict[str, Any]:
        with self._runtime_lock:
            return self._handle_command_packet(packet)

    def handle_direct_command_packet(self, packet: str) -> dict[str, Any]:
        if not self.config.legacy_command_ingress_enabled:
            return {
                "ok": False,
                "status": "disabled",
                "detail": (
                    "Legacy direct/Telegram command ingress is disabled. "
                    "Production commands now go only through Firebase."
                ),
                "http_status": 503,
            }
        with self._runtime_lock:
            result = self._handle_command_packet(packet)
        if result.get("ok"):
            self._start_background_snapshot(reason="direct_control")
        return result

    def _process_firebase_commands(self, greenhouse_key: str) -> None:
        if self.firebase_sync is None or not self.firebase_sync.enabled:
            return

        claimed = self.firebase_sync.claim_next_command(
            greenhouse_key=greenhouse_key,
            processing_by=self.config.firebase_processing_by,
            now_iso=self._now_iso(),
            default_expire_sec=self.config.firebase_command_expire_sec,
        )
        if claimed is None:
            return

        self._execute_firebase_command(claimed)

    def _execute_firebase_command(self, firebase_command: dict[str, Any]) -> None:
        command_id = str(firebase_command.get("command_id") or "")
        action = str(firebase_command.get("action") or "")
        greenhouse_key = self._greenhouse_key_for_target(
            str(firebase_command.get("target") or self.config.greenhouse_id)
        )
        LOGGER.info("Processing Firebase command %s action=%s", command_id, action)

        try:
            command = self._build_firebase_command_request(firebase_command)
        except Exception as exc:
            LOGGER.warning("Invalid Firebase command %s: %s", command_id, exc)
            if self.firebase_sync is not None:
                self.firebase_sync.complete_command(
                    greenhouse_key=greenhouse_key,
                    command_id=command_id,
                    status="error",
                    now_iso=self._now_iso(),
                    detail="Invalid Firebase command payload.",
                    error_message=str(exc),
                )
            return

        allowed, detail = self.guard.validate(command)
        if not allowed:
            LOGGER.warning("Rejected Firebase command %s: %s", command.cmd_id, detail)
            terminal_status = "expired" if detail == "command_expired" else "error"
            if self.firebase_sync is not None:
                self.firebase_sync.complete_command(
                    greenhouse_key=self._greenhouse_key_for_target(command.target),
                    command_id=command.cmd_id,
                    status=terminal_status,
                    now_iso=self._now_iso(),
                    detail=detail,
                    error_message=detail,
                )
            return

        if self.config.dry_run:
            LOGGER.info("DRY_RUN enabled, simulating Firebase command %s", command.cmd_id)
            if self.firebase_sync is not None:
                ts = self._now_iso()
                self.firebase_sync.update_active_command(
                    greenhouse_key=self._greenhouse_key_for_target(command.target),
                    command_id=command.cmd_id,
                    status="sent_to_esp",
                    now_iso=ts,
                    detail="DRY_RUN: command accepted, not sent to ESP.",
                    extra_fields={"sent_to_esp_at": ts},
                )
                ts = self._now_iso()
                self.firebase_sync.update_active_command(
                    greenhouse_key=self._greenhouse_key_for_target(command.target),
                    command_id=command.cmd_id,
                    status="esp_ack",
                    now_iso=ts,
                    detail="DRY_RUN: simulated ESP acknowledgement.",
                    extra_fields={"esp_ack_at": ts},
                )
                self.firebase_sync.complete_command(
                    greenhouse_key=self._greenhouse_key_for_target(command.target),
                    command_id=command.cmd_id,
                    status="done",
                    now_iso=self._now_iso(),
                    detail="DRY_RUN: simulated execution complete.",
                    device_state={
                        "target": command.target,
                        "firmware_cmd": command.action,
                        "dry_run": True,
                    },
                )
            self._start_background_snapshot(reason="firebase_command")
            return

        dispatch_started_at = monotonic()
        if self.firebase_sync is not None:
            sent_at = self._now_iso()
            self.firebase_sync.update_active_command(
                greenhouse_key=self._greenhouse_key_for_target(command.target),
                command_id=command.cmd_id,
                status="sent_to_esp",
                now_iso=sent_at,
                detail="Command sent from Raspberry to ESP via HTTP /control.",
                extra_fields={"sent_to_esp_at": sent_at},
            )
        try:
            receipt = self.controller_http.dispatch(command)
            raspberry_to_esp32_ms = duration_ms(dispatch_started_at)
            device_state = {
                "target": command.target,
                "firmware_cmd": receipt.firmware_cmd,
                "http_status": receipt.http_status,
                "target_url": receipt.target_url,
            }
            if self.firebase_sync is not None:
                ack_at = self._now_iso()
                self.firebase_sync.update_active_command(
                    greenhouse_key=self._greenhouse_key_for_target(command.target),
                    command_id=command.cmd_id,
                    status="esp_ack",
                    now_iso=ack_at,
                    detail="ESP HTTP /control accepted the command.",
                    extra_fields={
                        "esp_ack_at": ack_at,
                        "device_state": device_state,
                    },
                )
                self.firebase_sync.complete_command(
                    greenhouse_key=self._greenhouse_key_for_target(command.target),
                    command_id=command.cmd_id,
                    status="done",
                    now_iso=self._now_iso(),
                    detail="HTTP /control returned success; physical motion may continue in background.",
                    device_state=device_state,
                )

            if command.action == "update_config" and self.device_config_http is not None:
                try:
                    self._send_config_snapshot(
                        self.device_config_http.fetch_snapshot(self._now_iso())
                    )
                except Exception:
                    LOGGER.exception(
                        "Config update applied, but config snapshot refresh failed for %s",
                        command.cmd_id,
                    )

            self.perf_logger.log_event(
                "firebase_command_roundtrip",
                request_id=command.cmd_id,
                command=command.action,
                target=command.target,
                raspberry_to_esp32_ms=raspberry_to_esp32_ms,
                http_status=receipt.http_status,
                target_url=receipt.target_url,
                status="DONE",
            )
            self._start_background_snapshot(reason="firebase_command")
        except Exception as exc:
            LOGGER.exception("Failed to execute Firebase command %s", command.cmd_id)
            if self.firebase_sync is not None:
                self.firebase_sync.complete_command(
                    greenhouse_key=self._greenhouse_key_for_target(command.target),
                    command_id=command.cmd_id,
                    status="error",
                    now_iso=self._now_iso(),
                    detail=str(exc),
                    error_message=str(exc),
                )
            self.perf_logger.log_event(
                "firebase_command_roundtrip",
                request_id=command.cmd_id,
                command=command.action,
                target=command.target,
                total_ms=duration_ms(dispatch_started_at),
                status="ERROR",
                error=str(exc),
            )

    def _build_firebase_command_request(
        self,
        firebase_command: dict[str, Any],
    ) -> CommandRequest:
        command_id = str(firebase_command.get("command_id") or "").strip()
        if not command_id:
            raise ValueError("missing_command_id")

        raw_action = str(firebase_command.get("action") or "").strip()
        if not raw_action:
            raise ValueError("missing_action")

        params = firebase_command.get("params")
        command_params = dict(params) if isinstance(params, dict) else {}
        internal_action = raw_action
        if raw_action == "auto":
            internal_action = "set_mode"
            command_params["mode"] = "auto"
        elif raw_action == "manual":
            internal_action = "set_mode"
            command_params["mode"] = "manual"
        elif raw_action == "open_step":
            internal_action = "step_open"
        elif raw_action == "close_step":
            internal_action = "step_close"

        target = str(firebase_command.get("target") or self.config.greenhouse_id).strip()
        if not (target.startswith("g1") or target.startswith("g2")):
            raise ValueError(f"unsupported_target:{target}")

        created_at = str(firebase_command.get("created_at") or self._now_iso())
        expires_at = firebase_command.get("expires_at")
        ttl_sec = self.config.firebase_command_expire_sec
        if isinstance(expires_at, str):
            try:
                started_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                deadline = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                ttl_sec = max(1, int((deadline - started_at).total_seconds()))
            except ValueError:
                ttl_sec = self.config.firebase_command_expire_sec

        return CommandRequest(
            cmd_id=command_id,
            seq=int(firebase_command.get("seq") or 0),
            ts=created_at,
            ttl_sec=ttl_sec,
            target=target,
            action=internal_action,
            params=command_params,
        )

    def _refresh_greenhouse1_http_state(self) -> None:
        if self.greenhouse1_http is None or not self.greenhouse1_http.enabled:
            return
        refreshed = self.greenhouse1_http.refresh(
            previous=self.state_store.g1,
            now_iso=self._now_iso(),
        )
        changed = refreshed != self.state_store.g1
        with self._runtime_lock:
            self.state_store.replace_greenhouse1(refreshed)
        if changed:
            self._start_background_snapshot(reason="g1_http_change")

    @staticmethod
    def _greenhouse_key_for_target(target: str) -> str:
        return "g1" if target.startswith("g1") else "g2"

    def _start_background_snapshot(self, reason: str) -> None:
        """Avoid blocking direct HTTP responses on snapshot delivery."""
        thread = Thread(
            target=self._send_snapshot_in_background,
            args=(reason,),
            name=f"greenhouse-bridge-snapshot-{reason}",
            daemon=True,
        )
        thread.start()

    def _send_snapshot_in_background(self, reason: str) -> None:
        try:
            self._send_snapshot(reason=reason)
        except Exception:  # pragma: no cover - depends on live network state
            LOGGER.exception("Background snapshot failed for reason=%s", reason)

    def _handle_command_packet(self, packet: str) -> dict[str, Any]:
        history: list[dict[str, Any]] = []
        request_started_at = monotonic()
        try:
            command = self.crypto.open_command(packet)
        except Exception as exc:
            LOGGER.warning("Dropped invalid command packet: %s", exc)
            self.perf_logger.log_event(
                "command_roundtrip",
                command=None,
                target=None,
                total_ms=duration_ms(request_started_at),
                status="INVALID_PACKET",
                error=str(exc),
            )
            return {
                "ok": False,
                "status": "invalid_packet",
                "detail": str(exc),
                "history": history,
            }

        LOGGER.info(
            "Received command cmd_id=%s target=%s action=%s",
            command.cmd_id,
            command.target,
            command.action,
        )
        self._record_status(history, command.cmd_id, "received_by_raspberry")

        allowed, detail = self.guard.validate(command)
        if not allowed:
            self._record_status(history, command.cmd_id, "rejected", detail=detail)
            LOGGER.warning("Rejected command %s: %s", command.cmd_id, detail)
            self.perf_logger.log_event(
                "command_roundtrip",
                request_id=command.cmd_id,
                command=command.action,
                target=command.target,
                android_to_raspberry_ms=self._android_to_raspberry_ms(command.ts),
                total_ms=duration_ms(request_started_at),
                status="REJECTED",
                error=detail,
            )
            return {
                "ok": False,
                "cmd_id": command.cmd_id,
                "target": command.target,
                "action": command.action,
                "status": "rejected",
                "detail": detail,
                "history": history,
            }

        self._record_status(history, command.cmd_id, "validated")

        if command.target == "bridge" and command.action == "refresh_configs":
            return self._handle_refresh_configs(command=command, history=history)

        try:
            dispatch_started_at = monotonic()
            receipt = self.controller_http.dispatch(command)
            raspberry_to_esp32_ms = duration_ms(dispatch_started_at)
            device_state = {
                "target": command.target,
                "firmware_cmd": receipt.firmware_cmd,
                "http_status": receipt.http_status,
                "target_url": receipt.target_url,
            }
            self._record_status(
                history,
                command.cmd_id,
                "dispatched_to_http_control",
                detail="Local ESP32 /control accepted request",
                device_state=device_state,
            )
            self._record_status(
                history,
                command.cmd_id,
                "executing",
                detail="Command accepted by ESP32 controller",
                device_state=device_state,
            )
            final_detail = (
                "HTTP /control returned success; physical motion may continue in background"
            )
            self._record_status(
                history,
                command.cmd_id,
                "executed",
                detail=final_detail,
                device_state=device_state,
            )
            if command.action == "update_config" and self.device_config_http is not None:
                try:
                    self._send_config_snapshot(
                        self.device_config_http.fetch_snapshot(self._now_iso())
                    )
                except Exception:
                    LOGGER.exception(
                        "Config update applied, but config snapshot refresh failed for %s",
                        command.cmd_id,
                    )
            LOGGER.info("Executed command %s via %s", command.cmd_id, receipt.target_url)
            self.perf_logger.log_event(
                "command_roundtrip",
                request_id=command.cmd_id,
                command=command.action,
                target=command.target,
                firmware_cmd=receipt.firmware_cmd,
                target_url=receipt.target_url,
                http_status=receipt.http_status,
                android_to_raspberry_ms=self._android_to_raspberry_ms(command.ts),
                raspberry_to_esp32_ms=raspberry_to_esp32_ms,
                total_ms=duration_ms(request_started_at),
                status="OK",
            )
            return {
                "ok": True,
                "cmd_id": command.cmd_id,
                "target": command.target,
                "action": command.action,
                "status": "executed",
                "detail": final_detail,
                "device_state": device_state,
                "history": history,
            }
        except Exception as exc:
            LOGGER.exception("Failed to dispatch command %s", command.cmd_id)
            self._record_status(history, command.cmd_id, "failed", detail=str(exc))
            self.perf_logger.log_event(
                "command_roundtrip",
                request_id=command.cmd_id,
                command=command.action,
                target=command.target,
                android_to_raspberry_ms=self._android_to_raspberry_ms(command.ts),
                total_ms=duration_ms(request_started_at),
                status="FAILED",
                error=str(exc),
            )
            return {
                "ok": False,
                "cmd_id": command.cmd_id,
                "target": command.target,
                "action": command.action,
                "status": "failed",
                "detail": str(exc),
                "history": history,
            }

    def _handle_refresh_configs(
        self,
        command: Any,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self.device_config_http is None:
            detail = "config_http_client_unavailable"
            self._record_status(history, command.cmd_id, "failed", detail=detail)
            return {
                "ok": False,
                "cmd_id": command.cmd_id,
                "target": command.target,
                "action": command.action,
                "status": "failed",
                "detail": detail,
                "history": history,
            }

        try:
            snapshot = self.device_config_http.fetch_snapshot(self._now_iso())
            self._send_config_snapshot(snapshot)
            detail = "Configuration snapshot sent to Telegram bridge"
            self._record_status(history, command.cmd_id, "executed", detail=detail)
            return {
                "ok": True,
                "cmd_id": command.cmd_id,
                "target": command.target,
                "action": command.action,
                "status": "executed",
                "detail": detail,
                "history": history,
            }
        except Exception as exc:
            LOGGER.exception("Failed to refresh config snapshot for %s", command.cmd_id)
            self._record_status(history, command.cmd_id, "failed", detail=str(exc))
            return {
                "ok": False,
                "cmd_id": command.cmd_id,
                "target": command.target,
                "action": command.action,
                "status": "failed",
                "detail": str(exc),
                "history": history,
            }

    def _record_status(
        self,
        history: list[dict[str, Any]],
        cmd_id: str,
        status: str,
        detail: str | None = None,
        device_state: dict[str, Any] | None = None,
    ) -> None:
        ts = self._now_iso()
        history.append(
            {
                "status": status,
                "detail": detail,
                "ts": ts,
            }
        )
        self._send_status(
            cmd_id=cmd_id,
            status=status,
            detail=detail,
            device_state=device_state,
            ts=ts,
        )

    def _send_status(
        self,
        cmd_id: str,
        status: str,
        detail: str | None = None,
        device_state: dict[str, Any] | None = None,
        ts: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "result" if status in {"executing", "executed", "failed", "rejected"} else "ack",
            "cmd_id": cmd_id,
            "ts": ts or self._now_iso(),
            "status": status,
        }
        if detail is not None:
            payload["detail"] = detail
        if device_state is not None:
            payload["device_state"] = device_state

        packet = self.crypto.seal_command_status(payload)
        self.telegram.send_packet(packet)
        self.perf_logger.log_event(
            "command_status_packet",
            request_id=cmd_id,
            status=status,
            packet_size_bytes=len(packet.encode("utf-8")),
        )

    def _send_config_snapshot(self, snapshot: Any) -> None:
        payload = {
            "type": "config_snapshot",
            "ts": snapshot.ts,
            "g1": {
                "zone1": {
                    "tempOpen": snapshot.g1.zone1.temp_open,
                    "tempStep": snapshot.g1.zone1.temp_step,
                    "hystClose": snapshot.g1.zone1.hyst_close,
                    "maxTempCap": snapshot.g1.zone1.max_temp_cap,
                },
                "zone2": {
                    "tempOpen": snapshot.g1.zone2.temp_open,
                    "tempStep": snapshot.g1.zone2.temp_step,
                    "hystClose": snapshot.g1.zone2.hyst_close,
                    "maxTempCap": snapshot.g1.zone2.max_temp_cap,
                },
                "system": {
                    "sensorMs": snapshot.g1.system.sensor_sec,
                    "moveMs": snapshot.g1.system.move_sec,
                    "pauseMs": snapshot.g1.system.pause_sec,
                    "initCloseMs": snapshot.g1.system.init_close_sec,
                    "switchMs": snapshot.g1.system.switch_sec,
                    "extraCloseMs": snapshot.g1.system.extra_close_sec,
                    "fullTravelMs": snapshot.g1.system.full_travel_sec,
                    "enableWind": snapshot.g1.system.wind_enabled,
                    "windAlarmMps": snapshot.g1.system.wind_alarm_mps,
                    "enableRain": snapshot.g1.system.rain_enabled,
                    "rainAlarmPct": snapshot.g1.system.rain_alarm_pct,
                    "enableWater": snapshot.g1.system.water_enabled,
                },
                "serviceMotor": {
                    "serviceMotorMs": snapshot.g1.service_motor_sec,
                },
            },
            "g2": {
                "tempOpen": snapshot.g2.temp_open,
                "tempStep": snapshot.g2.temp_step,
                "hystClose": snapshot.g2.hyst_close,
                "maxTempCap": snapshot.g2.max_temp_cap,
                "sensorMs": snapshot.g2.sensor_sec,
                "moveMs": snapshot.g2.move_sec,
                "pauseMs": snapshot.g2.pause_sec,
                "initCloseMs": snapshot.g2.init_close_sec,
                "switchMs": snapshot.g2.switch_sec,
                "extraCloseMs": snapshot.g2.extra_close_sec,
            },
        }
        packet = self.crypto.seal_command_status(payload)
        self.telegram.send_packet(packet)
        self.perf_logger.log_event(
            "config_snapshot_packet",
            packet_size_bytes=len(packet.encode("utf-8")),
            status="OK",
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _android_to_raspberry_ms(command_ts: str | None) -> int | None:
        if not command_ts:
            return None
        try:
            started_at = datetime.fromisoformat(command_ts.replace("Z", "+00:00"))
        except ValueError:
            return None
        delta = datetime.now(timezone.utc) - started_at
        return max(0, int(delta.total_seconds() * 1000))


def build_app_from_env() -> GreenhouseBridgeApp:
    return build_app(BridgeConfig.from_env())


def build_app(config: BridgeConfig) -> GreenhouseBridgeApp:
    state_store = StateStore()
    mqtt_bridge = MqttBridge(config=config, state_store=state_store)
    controller_http = HttpController(config=config, state_store=state_store)
    crypto = CryptoBox(
        pi_to_app_key_b64=config.pi_to_app_key_b64,
        app_to_pi_key_b64=config.app_to_pi_key_b64,
        default_ttl_sec=config.command_ttl_sec,
    )
    telegram = TelegramTransport(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        poll_timeout_sec=config.telegram_poll_timeout_sec,
    )
    guard = CommandGuard()
    greenhouse1_http = Greenhouse1HttpClient(
        base_url=config.greenhouse1_base_url,
        timeout_sec=config.greenhouse_control_timeout_sec,
    )
    temperature_node_http = TemperatureNodeHttpClient(
        base_url=config.temperature_node_base_url,
        timeout_sec=config.greenhouse_control_timeout_sec,
    )
    device_config_http = DeviceConfigHttpClient(
        config=config,
        state_store=state_store,
        timeout_sec=config.greenhouse_control_timeout_sec,
    )
    app = GreenhouseBridgeApp(
        config=config,
        state_store=state_store,
        mqtt_bridge=mqtt_bridge,
        controller_http=controller_http,
        crypto=crypto,
        telegram=telegram,
        guard=guard,
        greenhouse1_http=greenhouse1_http,
        temperature_node_http=temperature_node_http,
        device_config_http=device_config_http,
        firebase_sync=FirebaseSync(config),
    )
    mqtt_bridge.on_relevant_update = app.handle_mqtt_update
    app.direct_command_http = DirectCommandHttpServer(
        host=config.direct_control_host,
        port=config.direct_control_port,
        handle_packet=app.handle_direct_command_packet,
    )
    return app


def main() -> int:
    config = BridgeConfig.from_env()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    LOGGER.info(
        "Loaded bridge config: %s",
        json.dumps(
            {
                "mqtt_host": config.mqtt_host,
                "mqtt_port": config.mqtt_port,
                "greenhouse1_base_url": config.greenhouse1_base_url or "<from-router-url>",
                "greenhouse2_base_url": config.greenhouse2_base_url or "<from-router-url>",
                "temperature_node_base_url": config.temperature_node_base_url or "<disabled>",
                "telemetry_period_sec": config.telemetry_period_sec,
                "post_command_snapshot_delay_sec": config.post_command_snapshot_delay_sec,
                "telegram_poll_timeout_sec": config.telegram_poll_timeout_sec,
                "command_polling_enabled": config.command_polling_enabled,
                "legacy_command_ingress_enabled": config.legacy_command_ingress_enabled,
                "direct_control_host": config.direct_control_host,
                "direct_control_port": config.direct_control_port,
            },
            ensure_ascii=False,
        ),
    )
    app = build_app(config)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
