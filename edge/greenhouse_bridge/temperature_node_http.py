from __future__ import annotations

import json
import re
import subprocess
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import TemperatureNodeState, TemperatureProbeState
from .performance import duration_ms, get_performance_logger


class TemperatureNodeHttpClient:
    """Fetches the standalone two-sensor ESP32 snapshot over local HTTP."""

    _number_pattern = re.compile(r"-?\d+(?:[.,]\d+)?")
    _ipv4_pattern = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
    _common_suffixes = tuple(range(20, 51)) + tuple(range(60, 71))

    def __init__(
        self,
        base_url: str,
        timeout_sec: float = 5.0,
        auto_discover: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.auto_discover = auto_discover
        self.perf_logger = get_performance_logger()
        self._resolved_base_url = self.base_url or None
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.base_url or self.auto_discover)

    def refresh(
        self,
        previous: TemperatureNodeState,
        now_iso: str,
        excluded_urls: tuple[str | None, ...] = (),
    ) -> TemperatureNodeState:
        if not self.enabled:
            return previous

        endpoint = self._resolved_base_url or self.base_url or previous.router_url
        if endpoint:
            try:
                payload = self._fetch_status(endpoint)
                self._resolved_base_url = endpoint
                return self._build_state(
                    payload=payload,
                    previous=previous,
                    now_iso=now_iso,
                    endpoint=endpoint,
                )
            except Exception as exc:
                self._last_error = f"{endpoint}: {exc}"

        discovered = self._discover_base_url(excluded_urls=excluded_urls)
        if discovered:
            try:
                payload = self._fetch_status(discovered)
                self._resolved_base_url = discovered
                return self._build_state(
                    payload=payload,
                    previous=previous,
                    now_iso=now_iso,
                    endpoint=discovered,
                    discovery_note="auto-discovered on Raspberry LAN",
                )
            except Exception as exc:
                self._last_error = f"{discovered}: {exc}"

        note = "Temperature node not discovered on local network."
        if self._last_error:
            note = f"{note} Last error: {self._last_error}"
        return TemperatureNodeState(
            ts=previous.ts,
            title=previous.title or "Temperature node / 3 sensors",
            sensor1=previous.sensor1,
            sensor2=previous.sensor2,
            outside=previous.outside,
            router_status="offline",
            router_url=endpoint or previous.router_url,
            wifi_rssi=previous.wifi_rssi,
            note=note,
        )

    def _build_state(
        self,
        payload: dict,
        previous: TemperatureNodeState,
        now_iso: str,
        endpoint: str,
        discovery_note: str | None = None,
    ) -> TemperatureNodeState:
        sensors = payload.get("sensors") or []
        sensor1_payload = sensors[0] if len(sensors) > 0 and isinstance(sensors[0], dict) else {}
        sensor2_payload = sensors[1] if len(sensors) > 1 and isinstance(sensors[1], dict) else {}
        outdoor_payload = sensors[2] if len(sensors) > 2 and isinstance(sensors[2], dict) else {}
        message = self._as_text(payload.get("message"))
        if discovery_note:
            message = f"{message} | {discovery_note}" if message else discovery_note

        return TemperatureNodeState(
            ts=now_iso,
            title="Temperature node / 3 sensors",
            sensor1=self._parse_probe(
                sensor1_payload,
                fallback=previous.sensor1,
                default_label="Thermostat",
            ),
            sensor2=self._parse_probe(
                sensor2_payload,
                fallback=previous.sensor2,
                default_label="Heat carrier",
            ),
            outside=self._parse_probe(
                outdoor_payload,
                fallback=previous.outside,
                default_label="Outdoor temperature",
            ),
            router_status=self._as_text(payload.get("routerStatus")) or "online",
            router_url=self._as_text(payload.get("routerUrl")) or endpoint,
            wifi_rssi=previous.wifi_rssi,
            note=message,
        )

    def _discover_base_url(self, excluded_urls: tuple[str | None, ...]) -> str | None:
        excluded_hosts = {
            self._extract_host(url)
            for url in excluded_urls
            if self._extract_host(url) is not None
        }
        if self._extract_host(self.base_url) is not None:
            excluded_hosts.discard(self._extract_host(self.base_url))

        for candidate in self._candidate_urls(excluded_hosts, excluded_urls):
            try:
                payload = self._fetch_status(candidate)
            except Exception:
                continue
            if self._looks_like_temperature_status(payload):
                return candidate
        return None

    def _candidate_urls(
        self,
        excluded_hosts: set[str],
        excluded_urls: tuple[str | None, ...],
    ) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def add(url: str | None) -> None:
            if not url:
                return
            normalized = url.rstrip("/")
            host = self._extract_host(normalized)
            if host is None or host in excluded_hosts or normalized in seen:
                return
            seen.add(normalized)
            candidates.append(normalized)

        add(self.base_url or None)
        add(self._resolved_base_url)

        for ip in self._neighbor_ips():
            add(f"http://{ip}")

        for prefix in self._seed_prefixes(excluded_urls):
            for suffix in self._common_suffixes:
                add(f"http://{prefix}.{suffix}")

        return candidates

    def _seed_prefixes(self, excluded_urls: tuple[str | None, ...]) -> set[str]:
        prefixes: set[str] = set()
        for url in excluded_urls:
            host = self._extract_host(url)
            if not host:
                continue
            parts = host.split(".")
            if len(parts) == 4:
                prefixes.add(".".join(parts[:3]))

        host = self._extract_host(self.base_url)
        if host:
            parts = host.split(".")
            if len(parts) == 4:
                prefixes.add(".".join(parts[:3]))

        return prefixes

    def _neighbor_ips(self) -> list[str]:
        try:
            proc = subprocess.run(
                ["ip", "neigh"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            return []

        ips: list[str] = []
        seen: set[str] = set()
        for line in proc.stdout.splitlines():
            match = self._ipv4_pattern.search(line)
            if match is None:
                continue
            ip = match.group(0)
            if ip in seen:
                continue
            seen.add(ip)
            ips.append(ip)
        return ips

    def _fetch_status(self, base_url: str) -> dict:
        started_at = monotonic()
        response_size_bytes = 0
        status = "OK"
        request = Request(
            f"{base_url}/status",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read().decode("utf-8", errors="replace")
                response_size_bytes = len(raw.encode("utf-8"))
        except HTTPError as exc:  # pragma: no cover - depends on local host
            status = "HTTP_ERROR"
            body = exc.read().decode("utf-8", errors="replace")
            response_size_bytes = len(body.encode("utf-8"))
            self.perf_logger.log_event(
                "esp32_poll",
                node="temperature_node",
                ip=self._extract_host(base_url),
                base_url=base_url,
                endpoint="/status",
                duration_ms=duration_ms(started_at),
                timeout_sec=self.timeout_sec,
                response_size_bytes=response_size_bytes,
                status=status,
                error=f"HTTP {exc.code}",
            )
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except URLError as exc:  # pragma: no cover - depends on local host
            status = "ERROR"
            self.perf_logger.log_event(
                "esp32_poll",
                node="temperature_node",
                ip=self._extract_host(base_url),
                base_url=base_url,
                endpoint="/status",
                duration_ms=duration_ms(started_at),
                timeout_sec=self.timeout_sec,
                response_size_bytes=response_size_bytes,
                status=status,
                error=str(exc.reason),
            )
            raise RuntimeError(str(exc.reason)) from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            status = "PARSE_ERROR"
            self.perf_logger.log_event(
                "esp32_poll",
                node="temperature_node",
                ip=self._extract_host(base_url),
                base_url=base_url,
                endpoint="/status",
                duration_ms=duration_ms(started_at),
                timeout_sec=self.timeout_sec,
                response_size_bytes=response_size_bytes,
                status=status,
                error=str(exc),
            )
            raise RuntimeError(f"Invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            status = "PARSE_ERROR"
            self.perf_logger.log_event(
                "esp32_poll",
                node="temperature_node",
                ip=self._extract_host(base_url),
                base_url=base_url,
                endpoint="/status",
                duration_ms=duration_ms(started_at),
                timeout_sec=self.timeout_sec,
                response_size_bytes=response_size_bytes,
                status=status,
                error="Unexpected /status payload",
            )
            raise RuntimeError("Unexpected /status payload")
        self.perf_logger.log_event(
            "esp32_poll",
            node="temperature_node",
            ip=self._extract_host(base_url),
            base_url=base_url,
            endpoint="/status",
            duration_ms=duration_ms(started_at),
            timeout_sec=self.timeout_sec,
            response_size_bytes=response_size_bytes,
            status=status,
        )
        return payload

    def _looks_like_temperature_status(self, payload: dict) -> bool:
        sensors = payload.get("sensors")
        if not isinstance(sensors, list) or len(sensors) < 2:
            return False
        return all(
            isinstance(item, dict) and any(key in item for key in ("tempLabel", "humidityLabel", "status"))
            for item in sensors[:2]
        )

    def _parse_probe(
        self,
        payload: dict,
        fallback: TemperatureProbeState,
        default_label: str,
    ) -> TemperatureProbeState:
        return TemperatureProbeState(
            label=default_label,
            temp=self._extract_float(payload.get("tempLabel")) if payload else fallback.temp,
            humidity=(
                self._extract_float(payload.get("humidityLabel"))
                if payload
                else fallback.humidity
            ),
            status=self._as_text(payload.get("status")) if payload else fallback.status,
            errors=self._extract_int(payload.get("errors")) if payload else fallback.errors,
            last_good_ago=(
                self._as_text(payload.get("lastGoodAgo"))
                if payload
                else fallback.last_good_ago
            ),
        )

    @classmethod
    def _extract_float(cls, value: object) -> float | None:
        text = cls._as_text(value)
        if not text:
            return None
        match = cls._number_pattern.search(text)
        if match is None:
            return None
        return float(match.group(0).replace(",", "."))

    @staticmethod
    def _extract_int(value: object) -> int | None:
        if value in ("", None):
            return None
        return int(value)

    @staticmethod
    def _extract_host(url: str | None) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        return parsed.hostname

    @staticmethod
    def _as_text(value: object) -> str | None:
        if value in ("", None):
            return None
        text = str(value).strip()
        return text or None
