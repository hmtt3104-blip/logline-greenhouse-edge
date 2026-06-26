from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import CommandRequest


class CommandGuard:
    """Last safety layer before a command reaches local ESP32 HTTP control."""

    _ALLOWED_TARGET_ACTIONS: dict[str, set[str]] = {
        "bridge": {"refresh_configs"},
        "g1": {"set_mode", "full_open", "full_close", "stop", "reset_alarm", "clear_wifi"},
        "g1.zone1": {"step_open", "step_close", "full_open", "full_close", "extra_close", "update_config"},
        "g1.zone2": {"step_open", "step_close", "full_open", "full_close", "extra_close", "update_config"},
        "g1.aux": {"aux_open", "aux_close", "aux_stop"},
        "g1.system": {"update_config"},
        "g1.service_motor": {"update_config"},
        "g2": {
            "set_mode",
            "step_open",
            "step_close",
            "full_open",
            "full_close",
            "extra_close",
            "stop",
            "clear_wifi",
            "update_config",
        },
    }

    def __init__(self) -> None:
        self._seen_command_ids: set[str] = set()

    def validate(self, command: CommandRequest) -> tuple[bool, str | None]:
        """Return (allowed, detail)."""
        allowed_actions = self._ALLOWED_TARGET_ACTIONS.get(command.target)
        if allowed_actions is None:
            return False, f"unsupported_target:{command.target}"
        if command.action not in allowed_actions:
            return False, f"unsupported_action_for_target:{command.target}:{command.action}"
        if command.cmd_id in self._seen_command_ids:
            return False, f"duplicate_command:{command.cmd_id}"
        if command.action == "set_mode":
            mode = command.params.get("mode")
            if mode not in {"auto", "manual"}:
                return False, "invalid_mode"
        if command.action == "update_config" and not command.params:
            return False, "empty_config_params"
        if self._is_expired(command):
            return False, "command_expired"

        self._seen_command_ids.add(command.cmd_id)
        return True, None

    @staticmethod
    def _is_expired(command: CommandRequest) -> bool:
        try:
            command_ts = datetime.fromisoformat(command.ts.replace("Z", "+00:00"))
        except ValueError:
            return True
        deadline = command_ts + timedelta(seconds=command.ttl_sec)
        return deadline < datetime.now(timezone.utc)
