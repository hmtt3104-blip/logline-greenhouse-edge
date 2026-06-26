from __future__ import annotations

from threading import Event
from typing import Any, Callable

from .config import BridgeConfig
from .performance import get_performance_logger
from .state_store import StateStore

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - depends on target runtime
    mqtt = None  # type: ignore[assignment]


class MqttBridge:
    """Adapter between local telemetry topics and the in-memory state store."""

    TELEMETRY_TOPICS: tuple[str, ...] = (
        "greenhouse/example/telemetry/greenhouse1/zone1/level",
        "greenhouse/example/telemetry/greenhouse1/zone1/temp",
        "greenhouse/example/telemetry/greenhouse1/zone1/humidity",
        "greenhouse/example/telemetry/greenhouse1/zone1/close_threshold",
        "greenhouse/example/telemetry/greenhouse1/zone1/state",
        "greenhouse/example/telemetry/greenhouse1/zone2/level",
        "greenhouse/example/telemetry/greenhouse1/zone2/temp",
        "greenhouse/example/telemetry/greenhouse1/zone2/humidity",
        "greenhouse/example/telemetry/greenhouse1/zone2/close_threshold",
        "greenhouse/example/telemetry/greenhouse1/zone2/state",
        "greenhouse/example/telemetry/greenhouse1/mode",
        "greenhouse/example/telemetry/greenhouse1/alarm",
        "greenhouse/example/telemetry/greenhouse1/water",
        "greenhouse/example/telemetry/greenhouse1/shade_state",
        "greenhouse/example/telemetry/greenhouse1/router_status",
        "greenhouse/example/telemetry/greenhouse1/router_url",
        "greenhouse/example/telemetry/greenhouse1/wifi_rssi",
        "greenhouse/example/telemetry/greenhouse1/reset_reason",
        "greenhouse/example/telemetry/greenhouse1/wifi_disconnect_reason",
        "greenhouse/example/telemetry/greenhouse1/wind",
        "greenhouse/example/telemetry/greenhouse1/rain",
        "greenhouse/example/status/greenhouse1",
        "greenhouse/example/events/greenhouse1",
        "greenhouse/example/telemetry/greenhouse2/level",
        "greenhouse/example/telemetry/greenhouse2/close_threshold",
        "greenhouse/example/telemetry/greenhouse2/state",
        "greenhouse/example/telemetry/greenhouse2/mode",
        "greenhouse/example/telemetry/greenhouse2/router_status",
        "greenhouse/example/telemetry/greenhouse2/router_url",
        "greenhouse/example/telemetry/greenhouse2/rtc_status",
        "greenhouse/example/telemetry/greenhouse2/sd_status",
        "greenhouse/example/telemetry/greenhouse2/last_action",
        "greenhouse/example/telemetry/greenhouse2/storage_status",
        "greenhouse/example/telemetry/greenhouse2/sensor_errors",
        "greenhouse/example/telemetry/greenhouse2/wifi_rssi",
        "greenhouse/example/telemetry/greenhouse2/wifi_disconnect_reason",
        "greenhouse/example/telemetry/greenhouse2/time",
        "greenhouse/example/telemetry/greenhouse2/humidity",
        "greenhouse/example/telemetry/greenhouse2/temp",
        "greenhouse/example/status/greenhouse2",
        "greenhouse/example/events/greenhouse2",
    )

    def __init__(self, config: BridgeConfig, state_store: StateStore) -> None:
        self.config = config
        self.state_store = state_store
        self.perf_logger = get_performance_logger()
        self._connected = Event()
        self._connect_error: str | None = None
        self._client: Any | None = None
        self.on_relevant_update: Callable[[str, bool], None] | None = None

    def subscription_topics(self) -> tuple[str, ...]:
        return self.TELEMETRY_TOPICS

    def start_telemetry_subscription(self) -> None:
        if mqtt is None:
            raise RuntimeError(
                "paho-mqtt is required for MQTT telemetry subscription. "
                "Install it from raspberry/requirements.txt on the target host."
            )

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(self.config.mqtt_host, self.config.mqtt_port, keepalive=60)
        self._client.loop_start()

        if not self._connected.wait(timeout=10):
            raise RuntimeError("MQTT bridge failed to connect within 10 seconds")
        if self._connect_error is not None:
            raise RuntimeError(self._connect_error)

    def stop(self) -> None:
        if self._client is None:
            return
        self._client.loop_stop()
        self._client.disconnect()
        self._client = None

    def handle_message(self, topic: str, payload: Any, *, retained: bool = False) -> None:
        if self.state_store.should_ignore_topic_payload(topic, payload):
            return

        topic_parts = topic.split("/")
        payload_size_bytes = len(payload) if isinstance(payload, bytes) else len(str(payload).encode("utf-8"))
        self.perf_logger.log_event(
            "mqtt_message",
            node=topic_parts[1] if len(topic_parts) > 1 else None,
            topic=topic,
            metric="/".join(topic_parts[2:]) if len(topic_parts) > 2 else None,
            payload_size_bytes=payload_size_bytes,
            status="OK",
        )
        changed = self.state_store.update_from_topic(topic, payload)
        if changed and self.on_relevant_update is not None:
            self.on_relevant_update(topic, retained)

    def _on_connect(self, client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        code = self._reason_code_value(reason_code)
        if code != 0:
            self._connect_error = f"MQTT connection failed with reason_code={reason_code}"
            self._connected.set()
            return
        for topic in self.subscription_topics():
            client.subscribe(topic)
        self._connected.set()

    def _on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        self.handle_message(message.topic, message.payload, retained=bool(getattr(message, "retain", False)))

    @staticmethod
    def _reason_code_value(reason_code: Any) -> int:
        if isinstance(reason_code, int):
            return reason_code
        value = getattr(reason_code, "value", None)
        if isinstance(value, int):
            return value
        try:
            return int(reason_code)
        except Exception:
            return -1
