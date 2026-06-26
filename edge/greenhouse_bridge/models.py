from dataclasses import dataclass, field
from typing import Any


ScalarValue = str | int | float | bool | None


@dataclass(slots=True)
class ZoneState:
    temp: float | None = None
    humidity: float | None = None
    level: float | None = None
    close_threshold: float | None = None
    state: str | None = None


@dataclass(slots=True)
class Greenhouse1State:
    ts: str | None = None
    mode: str | None = None
    alarm: str | None = None
    water: str | None = None
    shade_state: str | None = None
    router_status: str | None = None
    router_url: str | None = None
    wifi_rssi: int | None = None
    reset_reason: str | None = None
    wifi_disconnect_reason: str | None = None
    wind: ScalarValue = None
    rain: ScalarValue = None
    zone1: ZoneState = field(default_factory=ZoneState)
    zone2: ZoneState = field(default_factory=ZoneState)


@dataclass(slots=True)
class Greenhouse2State:
    ts: str | None = None
    mode: str | None = None
    state: str | None = None
    temp: float | None = None
    humidity: float | None = None
    level: float | None = None
    close_threshold: float | None = None
    last_action: str | None = None
    sensor_errors: int | None = None
    time: str | None = None
    rtc_status: str | None = None
    sd_status: str | None = None
    storage_status: str | None = None
    router_status: str | None = None
    router_url: str | None = None
    wifi_rssi: int | None = None
    wifi_disconnect_reason: str | None = None


@dataclass(slots=True)
class TemperatureProbeState:
    label: str | None = None
    temp: float | None = None
    humidity: float | None = None
    status: str | None = None
    errors: int | None = None
    last_good_ago: str | None = None


@dataclass(slots=True)
class TemperatureNodeState:
    ts: str | None = None
    title: str | None = None
    sensor1: TemperatureProbeState = field(default_factory=TemperatureProbeState)
    sensor2: TemperatureProbeState = field(default_factory=TemperatureProbeState)
    outside: TemperatureProbeState = field(default_factory=TemperatureProbeState)
    router_status: str | None = None
    router_url: str | None = None
    wifi_rssi: int | None = None
    note: str | None = None


@dataclass(slots=True)
class ZoneConfigState:
    temp_open: float | None = None
    temp_step: float | None = None
    hyst_close: float | None = None
    max_temp_cap: float | None = None


@dataclass(slots=True)
class Greenhouse1SystemConfigState:
    sensor_sec: float | None = None
    move_sec: float | None = None
    pause_sec: float | None = None
    init_close_sec: float | None = None
    switch_sec: float | None = None
    extra_close_sec: float | None = None
    full_travel_sec: float | None = None
    wind_enabled: bool | None = None
    wind_alarm_mps: float | None = None
    rain_enabled: bool | None = None
    rain_alarm_pct: float | None = None
    water_enabled: bool | None = None


@dataclass(slots=True)
class Greenhouse1ConfigState:
    zone1: ZoneConfigState = field(default_factory=ZoneConfigState)
    zone2: ZoneConfigState = field(default_factory=ZoneConfigState)
    system: Greenhouse1SystemConfigState = field(default_factory=Greenhouse1SystemConfigState)
    service_motor_sec: float | None = None


@dataclass(slots=True)
class Greenhouse2ConfigState:
    temp_open: float | None = None
    temp_step: float | None = None
    hyst_close: float | None = None
    max_temp_cap: float | None = None
    sensor_sec: float | None = None
    move_sec: float | None = None
    pause_sec: float | None = None
    init_close_sec: float | None = None
    switch_sec: float | None = None
    extra_close_sec: float | None = None


@dataclass(slots=True)
class DeviceConfigSnapshot:
    ts: str
    g1: Greenhouse1ConfigState = field(default_factory=Greenhouse1ConfigState)
    g2: Greenhouse2ConfigState = field(default_factory=Greenhouse2ConfigState)


@dataclass(slots=True)
class TelemetrySnapshot:
    seq: int
    ts: str
    g1: Greenhouse1State
    g2: Greenhouse2State
    temperature_node: TemperatureNodeState = field(default_factory=TemperatureNodeState)
    alerts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CommandRequest:
    cmd_id: str
    seq: int
    ts: str
    ttl_sec: int
    target: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class HttpDispatchReceipt:
    target_url: str
    firmware_cmd: str
    http_status: int


@dataclass(slots=True)
class CommandStatus:
    cmd_id: str
    ts: str
    status: str
    detail: str | None = None
    device_state: dict[str, Any] | None = None
