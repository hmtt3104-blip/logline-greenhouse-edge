from __future__ import annotations

import json
import re
from urllib.parse import urljoin
from urllib.request import urlopen

from .models import Greenhouse1State, ZoneState


class Greenhouse1HttpClient:
    """Fetch live two-zone greenhouse state from ESP32 `/status`."""

    _NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")

    def __init__(self, base_url: str, timeout_sec: float) -> None:
        self.base_url = base_url.strip()
        self.timeout_sec = timeout_sec

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def refresh(self, previous: Greenhouse1State, now_iso: str) -> Greenhouse1State:
        endpoint = self._normalize_base_url(previous.router_url or self.base_url)
        with urlopen(urljoin(endpoint, "status"), timeout=self.timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))

        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected /status payload")

        router_status = self._as_text(payload.get("routerBanner"))
        if router_status is None:
            router_status = "Wi-Fi OK" if self._as_bool(payload.get("routerConnected")) else "offline"

        return Greenhouse1State(
            ts=now_iso,
            mode=self._as_text(payload.get("mode")),
            alarm=self._as_text(payload.get("alarm")),
            water=self._as_text(payload.get("water")),
            shade_state=self._as_text(payload.get("auxState")) or self._as_text(payload.get("shadeState")),
            router_status=router_status,
            router_url=self._as_text(payload.get("routerUrl")) or endpoint.rstrip("/"),
            wifi_rssi=self._as_int(payload.get("wifiRssi")),
            reset_reason=self._as_text(payload.get("resetReason")),
            wifi_disconnect_reason=self._as_text(payload.get("wifiLastDisconnect")),
            wind=self._as_scalar(payload.get("wind")),
            rain=self._as_scalar(payload.get("rain")),
            zone1=self._parse_zone(payload, prefix="z1"),
            zone2=self._parse_zone(payload, prefix="z2"),
        )

    def _parse_zone(self, payload: dict[str, object], prefix: str) -> ZoneState:
        temp_raw = payload.get(f"{prefix}TempRaw")
        return ZoneState(
            temp=self._as_float(temp_raw if temp_raw not in (None, "") else payload.get(f"{prefix}Temp")),
            humidity=self._as_float(payload.get(f"{prefix}Hum")),
            level=self._as_float(payload.get(f"{prefix}Level")),
            close_threshold=self._as_float(payload.get(f"{prefix}Close")),
            state=self._as_text(payload.get(f"{prefix}State")),
        )

    @classmethod
    def _as_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text == "--":
            return None
        return text

    @classmethod
    def _as_float(cls, value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text or text == "--":
            return None
        match = cls._NUMBER_RE.search(text.replace(",", "."))
        if match is None:
            return None
        try:
            return float(match.group(0).replace(",", "."))
        except ValueError:
            return None

    @classmethod
    def _as_int(cls, value: object) -> int | None:
        parsed = cls._as_float(value)
        if parsed is None:
            return None
        return int(parsed)

    @staticmethod
    def _as_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def _as_scalar(cls, value: object) -> str | int | float | bool | None:
        text = cls._as_text(value)
        if text is None:
            return None
        lowered = text.lower()
        if lowered in {"true", "on", "yes"}:
            return True
        if lowered in {"false", "off", "no"}:
            return False
        try:
            if "." in text or "," in text:
                return float(text.replace(",", "."))
            return int(text)
        except ValueError:
            return text

    @staticmethod
    def _normalize_base_url(value: str | None) -> str:
        if not value:
            raise ValueError("Missing greenhouse1 base URL")
        base_url = value.strip()
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        if not base_url.endswith("/"):
            base_url = f"{base_url}/"
        return base_url
