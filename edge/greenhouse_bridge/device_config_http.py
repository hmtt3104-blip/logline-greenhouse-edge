from __future__ import annotations

import re
from urllib.parse import urljoin
from urllib.request import urlopen

from .config import BridgeConfig
from .models import (
    DeviceConfigSnapshot,
    Greenhouse1ConfigState,
    Greenhouse1SystemConfigState,
    Greenhouse2ConfigState,
    ZoneConfigState,
)
from .state_store import StateStore


class DeviceConfigHttpClient:
    """Fetch current editable config values from the ESP32 web UI."""

    _FORM_RE = re.compile(
        r"<form[^>]+method='POST'[^>]+action='/config'[^>]*>(?P<body>.*?)</form>",
        re.IGNORECASE | re.DOTALL,
    )
    _INPUT_RE = re.compile(
        r"<input[^>]+name='(?P<name>[^']+)'[^>]+value='(?P<value>[^']*)'[^>]*>",
        re.IGNORECASE | re.DOTALL,
    )
    _SCOPE_RE = re.compile(
        r"<input[^>]+type='hidden'[^>]+name='scope'[^>]+value='(?P<scope>[^']+)'[^>]*>",
        re.IGNORECASE | re.DOTALL,
    )
    _SELECT_RE = re.compile(
        r"<select[^>]+name='(?P<name>[^']+)'[^>]*>(?P<body>.*?)</select>",
        re.IGNORECASE | re.DOTALL,
    )
    _SELECTED_OPTION_RE = re.compile(
        r"<option[^>]+value='(?P<value>[^']*)'[^>]*selected[^>]*>",
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(self, config: BridgeConfig, state_store: StateStore, timeout_sec: float) -> None:
        self.config = config
        self.state_store = state_store
        self.timeout_sec = timeout_sec

    def fetch_snapshot(self, now_iso: str) -> DeviceConfigSnapshot:
        return DeviceConfigSnapshot(
            ts=now_iso,
            g1=self._fetch_g1(),
            g2=self._fetch_g2(),
        )

    def _fetch_g1(self) -> Greenhouse1ConfigState:
        html = self._fetch_root_html(
            self.state_store.g1.router_url or self.config.greenhouse1_base_url
        )
        forms = self._extract_forms(html)
        return Greenhouse1ConfigState(
            zone1=self._parse_zone_config(forms.get("z1", {})),
            zone2=self._parse_zone_config(forms.get("z2", {})),
            system=self._parse_g1_system_config(forms.get("global", {})),
            service_motor_sec=self._as_float(forms.get("serviceMotor", {}).get("serviceMotorMs")),
        )

    def _fetch_g2(self) -> Greenhouse2ConfigState:
        html = self._fetch_root_html(
            self.state_store.g2.router_url or self.config.greenhouse2_base_url
        )
        fields = next(iter(self._extract_forms(html).values()), {})
        return Greenhouse2ConfigState(
            temp_open=self._as_float(fields.get("tempOpen")),
            temp_step=self._as_float(fields.get("tempStep")),
            hyst_close=self._as_float(fields.get("hystClose")),
            max_temp_cap=self._as_float(fields.get("maxTempCap")),
            sensor_sec=self._as_float(fields.get("sensorMs")),
            move_sec=self._as_float(fields.get("moveMs")),
            pause_sec=self._as_float(fields.get("pauseMs")),
            init_close_sec=self._as_float(fields.get("initCloseMs")),
            switch_sec=self._as_float(fields.get("switchMs")),
            extra_close_sec=self._as_float(fields.get("extraCloseMs")),
        )

    def _fetch_root_html(self, base_url: str | None) -> str:
        root_url = urljoin(self._normalize_base_url(base_url), "")
        with urlopen(root_url, timeout=self.timeout_sec) as response:
            return response.read().decode("utf-8", errors="replace")

    def _extract_forms(self, html: str) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        forms = list(self._FORM_RE.finditer(html))
        for index, match in enumerate(forms):
            body = match.group("body")
            scope_match = self._SCOPE_RE.search(body)
            scope = scope_match.group("scope") if scope_match else f"form_{index}"
            fields = {
                input_match.group("name"): input_match.group("value")
                for input_match in self._INPUT_RE.finditer(body)
                if input_match.group("name") != "scope"
            }
            for select_match in self._SELECT_RE.finditer(body):
                selected_match = self._SELECTED_OPTION_RE.search(select_match.group("body"))
                if selected_match:
                    fields[select_match.group("name")] = selected_match.group("value")
            result[scope] = fields
        return result

    def _parse_zone_config(self, fields: dict[str, str]) -> ZoneConfigState:
        return ZoneConfigState(
            temp_open=self._as_float(fields.get("tempOpen")),
            temp_step=self._as_float(fields.get("tempStep")),
            hyst_close=self._as_float(fields.get("hystClose")),
            max_temp_cap=self._as_float(fields.get("maxTempCap")),
        )

    def _parse_g1_system_config(self, fields: dict[str, str]) -> Greenhouse1SystemConfigState:
        return Greenhouse1SystemConfigState(
            sensor_sec=self._as_float(fields.get("sensorMs")),
            move_sec=self._as_float(fields.get("moveMs")),
            pause_sec=self._as_float(fields.get("pauseMs")),
            init_close_sec=self._as_float(fields.get("initCloseMs")),
            switch_sec=self._as_float(fields.get("switchMs")),
            extra_close_sec=self._as_float(fields.get("extraCloseMs")),
            full_travel_sec=self._as_float(fields.get("fullTravelMs")),
            wind_enabled=self._as_bool(fields.get("enableWind")),
            wind_alarm_mps=self._as_float(fields.get("windAlarmMps")),
            rain_enabled=self._as_bool(fields.get("enableRain")),
            rain_alarm_pct=self._as_float(fields.get("rainAlarmPct")),
            water_enabled=self._as_bool(fields.get("enableWater")),
        )

    @staticmethod
    def _normalize_base_url(value: str | None) -> str:
        if not value:
            raise ValueError("Missing greenhouse base URL for config fetch")
        base_url = value.strip()
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        if not base_url.endswith("/"):
            base_url = f"{base_url}/"
        return base_url

    @staticmethod
    def _as_float(value: str | None) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _as_bool(value: str | None) -> bool | None:
        if value is None:
            return None
        return value in {"1", "true", "True", "yes", "on"}
