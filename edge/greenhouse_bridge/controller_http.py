from __future__ import annotations

from time import monotonic
from typing import Final
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import BridgeConfig
from .models import CommandRequest, HttpDispatchReceipt
from .performance import duration_ms, get_performance_logger
from .state_store import StateStore


class _NoRedirectHandler(HTTPRedirectHandler):
    """Keep POST handlers fast by not auto-following ESP redirects to the HTML home page."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


class HttpController:
    """Dispatch normalized commands into local ESP32 `/control` endpoints."""

    _DIRECT_COMMANDS: Final[dict[tuple[str, str], str]] = {
        ("g1", "stop"): "stop",
        ("g1", "reset_alarm"): "resetalarm",
        ("g1", "clear_wifi"): "clearwifi",
        ("g1.zone1", "step_open"): "z1_open",
        ("g1.zone1", "step_close"): "z1_close",
        ("g1.zone1", "full_open"): "z1_fullopen",
        ("g1.zone1", "full_close"): "z1_fullclose",
        ("g1.zone1", "extra_close"): "z1_extra",
        ("g1.zone2", "step_open"): "z2_open",
        ("g1.zone2", "step_close"): "z2_close",
        ("g1.zone2", "full_open"): "z2_fullopen",
        ("g1.zone2", "full_close"): "z2_fullclose",
        ("g1.zone2", "extra_close"): "z2_extra",
        ("g1.aux", "aux_open"): "aux_open",
        ("g1.aux", "aux_close"): "aux_close",
        ("g1.aux", "aux_stop"): "aux_stop",
        ("g2", "step_open"): "open",
        ("g2", "step_close"): "close",
        ("g2", "full_open"): "fullopen",
        ("g2", "full_close"): "fullclose",
        ("g2", "extra_close"): "extra",
        ("g2", "stop"): "stop",
        ("g2", "clear_wifi"): "clearwifi",
    }
    _G1_ZONE_CONFIG_FIELDS: Final[set[str]] = {
        "tempOpen",
        "tempStep",
        "hystClose",
        "maxTempCap",
    }
    _G1_SYSTEM_CONFIG_FIELDS: Final[set[str]] = {
        "sensorMs",
        "moveMs",
        "pauseMs",
        "initCloseMs",
        "switchMs",
        "extraCloseMs",
        "fullTravelMs",
        "enableWind",
        "windAlarmMps",
        "enableRain",
        "rainAlarmPct",
        "enableWater",
    }
    _G2_CONFIG_FIELDS: Final[set[str]] = {
        "tempOpen",
        "tempStep",
        "hystClose",
        "maxTempCap",
        "sensorMs",
        "moveMs",
        "pauseMs",
        "initCloseMs",
        "switchMs",
        "extraCloseMs",
    }

    def __init__(self, config: BridgeConfig, state_store: StateStore) -> None:
        self.config = config
        self.state_store = state_store
        self.perf_logger = get_performance_logger()
        self._no_redirect_opener = build_opener(_NoRedirectHandler())
        self._g1_compound_commands: dict[str, tuple[str, str]] = {
            "full_open": ("z1_fullopen", "z2_fullopen"),
            "full_close": ("z1_fullclose", "z2_fullclose"),
        }

    def dispatch(self, command: CommandRequest) -> HttpDispatchReceipt:
        started_at = monotonic()
        if command.action == "update_config":
            control_url, body, firmware_cmd = self._build_config_request(command)
        elif command.target == "g1" and command.action in self._g1_compound_commands:
            control_url = self._resolve_control_url(command.target)
            firmware_cmds = self._g1_compound_commands[command.action]
            return self._dispatch_compound_g1_command(
                command=command,
                control_url=control_url,
                firmware_cmds=firmware_cmds,
                started_at=started_at,
            )
        else:
            firmware_cmd = self._map_command(command)
            control_url = self._resolve_control_url(command.target)
            body = urlencode({"cmd": firmware_cmd}).encode("utf-8")
        return self._dispatch_single_request(
            command=command,
            control_url=control_url,
            firmware_cmd=firmware_cmd,
            body=body,
            started_at=started_at,
        )

    def _dispatch_single_request(
        self,
        *,
        command: CommandRequest,
        control_url: str,
        firmware_cmd: str,
        body: bytes,
        started_at: float,
    ) -> HttpDispatchReceipt:
        request = Request(
            control_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with self._no_redirect_opener.open(
                request,
                timeout=self.config.greenhouse_control_timeout_sec,
            ) as response:
                return self._build_success_receipt(
                    command=command,
                    control_url=control_url,
                    firmware_cmd=firmware_cmd,
                    started_at=started_at,
                    http_status=response.status,
                    response_body=response.read(),
                )
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                return self._build_success_receipt(
                    command=command,
                    control_url=control_url,
                    firmware_cmd=firmware_cmd,
                    started_at=started_at,
                    http_status=exc.code,
                    response_body=exc.read(),
                    redirect_location=exc.headers.get("Location"),
                )
            self.perf_logger.log_event(
                "esp32_http_dispatch",
                request_id=command.cmd_id,
                command=command.action,
                target=command.target,
                firmware_cmd=firmware_cmd,
                ip=urlparse(control_url).hostname,
                target_url=control_url,
                endpoint=urlparse(control_url).path or "/",
                duration_ms=duration_ms(started_at),
                timeout_sec=self.config.greenhouse_control_timeout_sec,
                status="ERROR",
                error=str(exc),
                http_status=exc.code,
            )
            raise
        except Exception as exc:
            self.perf_logger.log_event(
                "esp32_http_dispatch",
                request_id=command.cmd_id,
                command=command.action,
                target=command.target,
                firmware_cmd=firmware_cmd,
                ip=urlparse(control_url).hostname,
                target_url=control_url,
                endpoint=urlparse(control_url).path or "/",
                duration_ms=duration_ms(started_at),
                timeout_sec=self.config.greenhouse_control_timeout_sec,
                status="ERROR",
                error=str(exc),
            )
            raise

    def _dispatch_compound_g1_command(
        self,
        *,
        command: CommandRequest,
        control_url: str,
        firmware_cmds: tuple[str, str],
        started_at: float,
    ) -> HttpDispatchReceipt:
        total_response_size = 0
        last_status = 200
        redirect_locations: list[str] = []

        try:
            for firmware_cmd in firmware_cmds:
                request = Request(
                    control_url,
                    data=urlencode({"cmd": firmware_cmd}).encode("utf-8"),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                try:
                    with self._no_redirect_opener.open(
                        request,
                        timeout=self.config.greenhouse_control_timeout_sec,
                    ) as response:
                        last_status = response.status
                        total_response_size += len(response.read())
                except HTTPError as exc:
                    if exc.code not in {301, 302, 303, 307, 308}:
                        raise
                    last_status = exc.code
                    total_response_size += len(exc.read())
                    redirect_location = exc.headers.get("Location")
                    if redirect_location:
                        redirect_locations.append(redirect_location)

            firmware_cmd = "+".join(firmware_cmds)
            receipt = HttpDispatchReceipt(
                target_url=control_url,
                firmware_cmd=firmware_cmd,
                http_status=last_status,
            )
            self.perf_logger.log_event(
                "esp32_http_dispatch",
                request_id=command.cmd_id,
                command=command.action,
                target=command.target,
                firmware_cmd=firmware_cmd,
                ip=urlparse(control_url).hostname,
                target_url=control_url,
                endpoint=urlparse(control_url).path or "/",
                duration_ms=duration_ms(started_at),
                timeout_sec=self.config.greenhouse_control_timeout_sec,
                http_status=last_status,
                response_size_bytes=total_response_size,
                redirect_location=",".join(redirect_locations) if redirect_locations else None,
                status="OK",
            )
            return receipt
        except Exception as exc:
            self.perf_logger.log_event(
                "esp32_http_dispatch",
                request_id=command.cmd_id,
                command=command.action,
                target=command.target,
                firmware_cmd="+".join(firmware_cmds),
                ip=urlparse(control_url).hostname,
                target_url=control_url,
                endpoint=urlparse(control_url).path or "/",
                duration_ms=duration_ms(started_at),
                timeout_sec=self.config.greenhouse_control_timeout_sec,
                status="ERROR",
                error=str(exc),
            )
            raise

    def _build_success_receipt(
        self,
        command: CommandRequest,
        control_url: str,
        firmware_cmd: str,
        started_at: float,
        http_status: int,
        response_body: bytes,
        redirect_location: str | None = None,
    ) -> HttpDispatchReceipt:
        receipt = HttpDispatchReceipt(
            target_url=control_url,
            firmware_cmd=firmware_cmd,
            http_status=http_status,
        )
        self.perf_logger.log_event(
            "esp32_http_dispatch",
            request_id=command.cmd_id,
            command=command.action,
            target=command.target,
            firmware_cmd=firmware_cmd,
            ip=urlparse(control_url).hostname,
            target_url=control_url,
            endpoint=urlparse(control_url).path or "/",
            duration_ms=duration_ms(started_at),
            timeout_sec=self.config.greenhouse_control_timeout_sec,
            http_status=http_status,
            response_size_bytes=len(response_body),
            redirect_location=redirect_location,
            status="OK",
        )
        return receipt

    def _map_command(self, command: CommandRequest) -> str:
        if command.action == "set_mode":
            mode = command.params.get("mode")
            if mode not in {"auto", "manual"}:
                raise ValueError("set_mode requires params.mode=auto|manual")
            if command.target not in {"g1", "g2"}:
                raise ValueError("set_mode is only supported for g1 or g2")
            return mode

        firmware_cmd = self._DIRECT_COMMANDS.get((command.target, command.action))
        if firmware_cmd is None:
            raise ValueError(f"Unsupported command mapping: {command.target}.{command.action}")
        return firmware_cmd

    def _resolve_control_url(self, target: str) -> str:
        if target.startswith("g1"):
            base_url = self._normalize_base_url(
                self.state_store.g1.router_url or self.config.greenhouse1_base_url
            )
        elif target.startswith("g2"):
            base_url = self._normalize_base_url(
                self.state_store.g2.router_url or self.config.greenhouse2_base_url
            )
        else:
            raise ValueError(f"Unsupported target: {target}")

        return urljoin(base_url, "control")

    def _resolve_config_url(self, target: str) -> str:
        if target.startswith("g1"):
            base_url = self._normalize_base_url(
                self.state_store.g1.router_url or self.config.greenhouse1_base_url
            )
        elif target.startswith("g2"):
            base_url = self._normalize_base_url(
                self.state_store.g2.router_url or self.config.greenhouse2_base_url
            )
        else:
            raise ValueError(f"Unsupported target for config update: {target}")
        return urljoin(base_url, "config")

    def _build_config_request(self, command: CommandRequest) -> tuple[str, bytes, str]:
        params = dict(command.params)
        if not params:
            raise ValueError("update_config requires non-empty params")

        body_params: dict[str, str] = {}
        config_label = "config"
        if command.target == "g1.zone1":
            body_params["scope"] = "z1"
            body_params.update(self._filter_and_stringify(params, self._G1_ZONE_CONFIG_FIELDS))
            config_label = "config:g1.zone1"
        elif command.target == "g1.zone2":
            body_params["scope"] = "z2"
            body_params.update(self._filter_and_stringify(params, self._G1_ZONE_CONFIG_FIELDS))
            config_label = "config:g1.zone2"
        elif command.target == "g1.system":
            body_params["scope"] = "global"
            body_params.update(self._filter_and_stringify(params, self._G1_SYSTEM_CONFIG_FIELDS))
            config_label = "config:g1.system"
        elif command.target == "g1.service_motor":
            body_params["scope"] = "serviceMotor"
            body_params.update(self._filter_and_stringify(params, {"serviceMotorMs"}))
            config_label = "config:g1.service_motor"
        elif command.target == "g2":
            body_params.update(self._filter_and_stringify(params, self._G2_CONFIG_FIELDS))
            config_label = "config:g2"
        else:
            raise ValueError(f"Unsupported target for update_config: {command.target}")

        if not body_params or body_params == {"scope": body_params.get("scope")}:
            raise ValueError(f"No supported config params for {command.target}")

        return (
            self._resolve_config_url(command.target),
            urlencode(body_params).encode("utf-8"),
            config_label,
        )

    @staticmethod
    def _filter_and_stringify(params: dict[str, object], allowed: set[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in params.items():
            if key not in allowed or value is None:
                continue
            if isinstance(value, bool):
                result[key] = "1" if value else "0"
            else:
                result[key] = str(value)
        return result

    @staticmethod
    def _normalize_base_url(value: str | None) -> str:
        if not value:
            raise ValueError("Missing greenhouse base URL")
        base_url = value.strip()
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        if not base_url.endswith("/"):
            base_url = f"{base_url}/"
        return base_url
