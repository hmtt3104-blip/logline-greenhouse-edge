from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from .models import (
    Greenhouse1State,
    Greenhouse2State,
    ScalarValue,
    TelemetrySnapshot,
    TemperatureNodeState,
    TemperatureProbeState,
)


TopicHandler = Callable[[Any], bool]


class StateStore:
    """In-memory source of truth filled from local MQTT telemetry."""

    _GREENHOUSE2_IGNORED_EVENT_PREFIXES = (
        "Час синхронізовано",
    )
    _GREENHOUSE2_IGNORED_EVENT_MESSAGES = {
        "Web command received",
    }

    def __init__(self) -> None:
        self.g1 = Greenhouse1State()
        self.g2 = Greenhouse2State()
        self.t3 = TemperatureNodeState(
            title="Температурний вузол",
            sensor1=TemperatureProbeState(label="Термостат"),
            sensor2=TemperatureProbeState(label="Теплоносій"),
        )
        self._seq = 0
        self._topic_handlers: dict[str, TopicHandler] = {
            "greenhouse/example/telemetry/greenhouse1/zone1/temp": self._dynamic_setter(
                lambda: self.g1.zone1, "temp", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse1/zone1/humidity": self._dynamic_setter(
                lambda: self.g1.zone1, "humidity", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse1/zone1/level": self._dynamic_setter(
                lambda: self.g1.zone1, "level", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse1/zone1/close_threshold": self._dynamic_setter(
                lambda: self.g1.zone1, "close_threshold", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse1/zone1/state": self._dynamic_setter(
                lambda: self.g1.zone1, "state", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse1/zone2/temp": self._dynamic_setter(
                lambda: self.g1.zone2, "temp", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse1/zone2/humidity": self._dynamic_setter(
                lambda: self.g1.zone2, "humidity", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse1/zone2/level": self._dynamic_setter(
                lambda: self.g1.zone2, "level", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse1/zone2/close_threshold": self._dynamic_setter(
                lambda: self.g1.zone2, "close_threshold", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse1/zone2/state": self._dynamic_setter(
                lambda: self.g1.zone2, "state", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse1/mode": self._dynamic_setter(
                lambda: self.g1, "mode", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse1/alarm": self._dynamic_setter(
                lambda: self.g1, "alarm", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse1/water": self._dynamic_setter(
                lambda: self.g1, "water", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse1/shade_state": self._dynamic_setter(
                lambda: self.g1, "shade_state", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse1/router_status": self._dynamic_setter(
                lambda: self.g1, "router_status", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse1/router_url": self._dynamic_setter(
                lambda: self.g1, "router_url", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse1/wifi_rssi": self._dynamic_setter(
                lambda: self.g1, "wifi_rssi", self._as_int
            ),
            "greenhouse/example/telemetry/greenhouse1/reset_reason": self._dynamic_setter(
                lambda: self.g1, "reset_reason", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse1/wifi_disconnect_reason": self._dynamic_setter(
                lambda: self.g1, "wifi_disconnect_reason", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse1/wind": self._dynamic_setter(
                lambda: self.g1, "wind", self._as_scalar
            ),
            "greenhouse/example/telemetry/greenhouse1/rain": self._dynamic_setter(
                lambda: self.g1, "rain", self._as_scalar
            ),
            "greenhouse/example/status/greenhouse1": self._dynamic_setter(
                lambda: self.g1, "router_status", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse2/temp": self._setter(self.g2, "temp", self._as_float),
            "greenhouse/example/telemetry/greenhouse2/humidity": self._setter(
                self.g2, "humidity", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse2/level": self._setter(
                self.g2, "level", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse2/close_threshold": self._setter(
                self.g2, "close_threshold", self._as_float
            ),
            "greenhouse/example/telemetry/greenhouse2/state": self._setter(
                self.g2, "state", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse2/mode": self._setter(self.g2, "mode", self._as_text),
            "greenhouse/example/telemetry/greenhouse2/last_action": self._setter(
                self.g2, "last_action", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse2/sensor_errors": self._setter(
                self.g2, "sensor_errors", self._as_int
            ),
            "greenhouse/example/telemetry/greenhouse2/time": self._setter(self.g2, "time", self._as_text),
            "greenhouse/example/telemetry/greenhouse2/rtc_status": self._setter(
                self.g2, "rtc_status", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse2/sd_status": self._setter(
                self.g2, "sd_status", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse2/storage_status": self._setter(
                self.g2, "storage_status", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse2/router_status": self._setter(
                self.g2, "router_status", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse2/router_url": self._setter(
                self.g2, "router_url", self._as_text
            ),
            "greenhouse/example/telemetry/greenhouse2/wifi_rssi": self._setter(
                self.g2, "wifi_rssi", self._as_int
            ),
            "greenhouse/example/telemetry/greenhouse2/wifi_disconnect_reason": self._setter(
                self.g2, "wifi_disconnect_reason", self._as_text
            ),
            "greenhouse/example/status/greenhouse2": self._setter(
                self.g2, "router_status", self._as_text
            ),
            "greenhouse/example/events/greenhouse2": self._handle_greenhouse2_event,
        }

    @classmethod
    def should_ignore_topic_payload(cls, topic: str, payload: Any) -> bool:
        if topic != "greenhouse/example/events/greenhouse2":
            return False
        return cls._extract_greenhouse2_event_message(payload) is None

    def update_from_topic(self, topic: str, payload: Any) -> bool:
        """Map local MQTT topics into the unified greenhouse state."""
        handler = self._topic_handlers.get(topic)
        if handler is None:
            return False

        changed = handler(payload)
        if not changed:
            return False

        if topic.startswith("farm/greenhouse1/"):
            self.g1.ts = self._now_iso()
        elif topic.startswith("farm/greenhouse2/"):
            self.g2.ts = self._now_iso()
        return True

    def replace_temperature_node(self, node: TemperatureNodeState) -> None:
        self.t3 = node

    def replace_greenhouse1(self, greenhouse: Greenhouse1State) -> None:
        self.g1 = greenhouse

    def next_snapshot(self, now_iso: str) -> TelemetrySnapshot:
        self._seq += 1
        return TelemetrySnapshot(
            seq=self._seq,
            ts=now_iso,
            g1=deepcopy(self.g1),
            g2=deepcopy(self.g2),
            temperature_node=deepcopy(self.t3),
            alerts=self._build_alerts(),
        )

    def _build_alerts(self) -> list[str]:
        alerts: list[str] = []
        if self._is_active_alarm(self.g1.alarm):
            alerts.append(f"g1 alarm={self.g1.alarm}")
        if self._looks_offline(self.g1.router_status):
            alerts.append("g1 offline")
        if self._looks_offline(self.g2.router_status):
            alerts.append("g2 offline")
        if self.g2.sensor_errors not in (None, 0):
            alerts.append(f"g2 sensor_errors={self.g2.sensor_errors}")
        if self._looks_offline(self.t3.router_status):
            alerts.append("t3 offline")
        if self.t3.sensor1.errors not in (None, 0):
            alerts.append(f"t3 sensor1_errors={self.t3.sensor1.errors}")
        if self.t3.sensor2.errors not in (None, 0):
            alerts.append(f"t3 sensor2_errors={self.t3.sensor2.errors}")
        return alerts

    @staticmethod
    def _setter(target: Any, field_name: str, converter: Callable[[Any], Any]) -> TopicHandler:
        return StateStore._dynamic_setter(lambda: target, field_name, converter)

    @staticmethod
    def _dynamic_setter(
        target_getter: Callable[[], Any],
        field_name: str,
        converter: Callable[[Any], Any],
    ) -> TopicHandler:
        def apply(payload: Any) -> bool:
            target = target_getter()
            new_value = converter(payload)
            old_value = getattr(target, field_name)
            setattr(target, field_name, new_value)
            return old_value != new_value

        return apply

    def _handle_greenhouse2_event(self, payload: Any) -> bool:
        message = self._extract_greenhouse2_event_message(payload)
        if message is None:
            return False
        old_value = self.g2.last_action
        self.g2.last_action = message
        return old_value != message

    @staticmethod
    def _coerce_payload(payload: Any) -> Any:
        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace").strip()
        if isinstance(payload, str):
            return payload.strip()
        return payload

    @classmethod
    def _as_text(cls, payload: Any) -> str | None:
        value = cls._coerce_payload(payload)
        if value in ("", None):
            return None
        return str(value)

    @classmethod
    def _as_float(cls, payload: Any) -> float | None:
        value = cls._coerce_payload(payload)
        if value in ("", None):
            return None
        return float(value)

    @classmethod
    def _as_int(cls, payload: Any) -> int | None:
        value = cls._coerce_payload(payload)
        if value in ("", None):
            return None
        return int(float(value))

    @classmethod
    def _as_scalar(cls, payload: Any) -> ScalarValue:
        value = cls._coerce_payload(payload)
        if value in ("", None):
            return None
        if isinstance(value, (bool, int, float)):
            return value
        text = str(value).strip()
        lowered = text.lower()
        if lowered in {"true", "on", "yes"}:
            return True
        if lowered in {"false", "off", "no"}:
            return False
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text

    @classmethod
    def _extract_greenhouse2_event_message(cls, payload: Any) -> str | None:
        value = cls._coerce_payload(payload)
        if value in ("", None):
            return None

        message: str | None = None
        if isinstance(value, dict):
            raw_message = value.get("message")
            if raw_message is not None:
                message = str(raw_message).strip()
        else:
            text = str(value).strip()
            if text.startswith("{") and text.endswith("}"):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    raw_message = parsed.get("message")
                    if raw_message is not None:
                        message = str(raw_message).strip()
            if message is None:
                message = text

        if not message:
            return None
        if message in cls._GREENHOUSE2_IGNORED_EVENT_MESSAGES:
            return None
        if any(message.startswith(prefix) for prefix in cls._GREENHOUSE2_IGNORED_EVENT_PREFIXES):
            return None
        return message

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _is_active_alarm(value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() not in {
            "0",
            "off",
            "ok",
            "idle",
            "none",
            "false",
            "normal",
            "норма",
        }

    @staticmethod
    def _looks_offline(value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {"offline", "disconnected", "lost"}
