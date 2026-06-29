from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class BridgeConfig:
    telegram_bot_token: str
    telegram_chat_id: str
    mqtt_host: str
    mqtt_port: int
    telegram_egress_enabled: bool = False
    greenhouse1_base_url: str = ""
    greenhouse2_base_url: str = ""
    temperature_node_base_url: str = ""
    greenhouse_control_timeout_sec: float = 5.0
    telegram_poll_timeout_sec: int = 20
    telemetry_period_sec: int = 120
    post_command_snapshot_delay_sec: float = 2.0
    command_ttl_sec: int = 60
    loop_idle_sleep_sec: float = 0.25
    direct_control_host: str = "127.0.0.1"
    direct_control_port: int = 8787
    log_level: str = "INFO"
    pi_to_app_key_b64: str = ""
    app_to_pi_key_b64: str = ""
    command_polling_enabled: bool = False
    legacy_command_ingress_enabled: bool = False
    firebase_enabled: bool = False
    firebase_database_url: str = ""
    firebase_service_account_json: str = ""
    greenhouse_id: str = "g2"
    firebase_g1_state_path: str = "examples/greenhouse1/state"
    firebase_g1_commands_pending_path: str = "examples/greenhouse1/commands/pending"
    firebase_g1_commands_history_path: str = "examples/greenhouse1/commands/history"
    firebase_g2_state_path: str = "examples/greenhouse2/state"
    firebase_g2_commands_pending_path: str = "examples/greenhouse2/commands/pending"
    firebase_g2_commands_history_path: str = "examples/greenhouse2/commands/history"
    firebase_t3_state_path: str = "examples/temperature-node/state"
    firebase_processing_by: str = "logline_greenhouse_edge"
    firebase_poll_interval_sec: float = 1.0
    firebase_command_expire_sec: int = 90
    firebase_stale_state_sec: int = 45
    greenhouse1_status_poll_interval_sec: float = 5.0
    dry_run: bool = True

    @classmethod
    def from_env(cls, prefix: str = "GREENHOUSE_BRIDGE_") -> "BridgeConfig":
        firebase_enabled = cls._bool_env(os.getenv(f"{prefix}FIREBASE_ENABLED", "0"))
        telegram_egress_enabled = cls._bool_env(
            os.getenv(f"{prefix}TELEGRAM_EGRESS_ENABLED", "0")
        )
        command_polling_enabled = cls._bool_env(
            os.getenv(f"{prefix}COMMAND_POLLING_ENABLED", "0")
        )
        legacy_command_ingress_enabled = cls._bool_env(
            os.getenv(f"{prefix}LEGACY_COMMAND_INGRESS_ENABLED", "0")
        )
        telegram_required = (
            telegram_egress_enabled
            or command_polling_enabled
            or legacy_command_ingress_enabled
        )
        crypto_required = telegram_required
        return cls(
            telegram_bot_token=cls._require_if(
                prefix,
                "TELEGRAM_BOT_TOKEN",
                telegram_required,
            ),
            telegram_chat_id=cls._require_if(
                prefix,
                "TELEGRAM_CHAT_ID",
                telegram_required,
            ),
            telegram_egress_enabled=telegram_egress_enabled,
            mqtt_host=cls._require(prefix, "MQTT_HOST"),
            mqtt_port=int(cls._require(prefix, "MQTT_PORT")),
            greenhouse1_base_url=os.getenv(f"{prefix}GREENHOUSE1_BASE_URL", "").strip(),
            greenhouse2_base_url=os.getenv(f"{prefix}GREENHOUSE2_BASE_URL", "").strip(),
            temperature_node_base_url=os.getenv(
                f"{prefix}TEMPERATURE_NODE_BASE_URL", ""
            ).strip(),
            greenhouse_control_timeout_sec=float(
                os.getenv(f"{prefix}GREENHOUSE_CONTROL_TIMEOUT_SEC", "5.0")
            ),
            telegram_poll_timeout_sec=int(os.getenv(f"{prefix}TELEGRAM_POLL_TIMEOUT_SEC", "20")),
            telemetry_period_sec=int(os.getenv(f"{prefix}TELEMETRY_PERIOD_SEC", "120")),
            post_command_snapshot_delay_sec=float(
                os.getenv(f"{prefix}POST_COMMAND_SNAPSHOT_DELAY_SEC", "2.0")
            ),
            command_ttl_sec=int(os.getenv(f"{prefix}COMMAND_TTL_SEC", "60")),
            loop_idle_sleep_sec=float(os.getenv(f"{prefix}LOOP_IDLE_SLEEP_SEC", "0.25")),
            direct_control_host=(
                os.getenv(f"{prefix}DIRECT_CONTROL_HOST", "127.0.0.1").strip() or "127.0.0.1"
            ),
            direct_control_port=int(os.getenv(f"{prefix}DIRECT_CONTROL_PORT", "8787")),
            log_level=os.getenv(f"{prefix}LOG_LEVEL", "INFO").strip() or "INFO",
            pi_to_app_key_b64=cls._require_if(prefix, "PI_TO_APP_KEY_B64", crypto_required),
            app_to_pi_key_b64=cls._require_if(prefix, "APP_TO_PI_KEY_B64", crypto_required),
            command_polling_enabled=command_polling_enabled,
            legacy_command_ingress_enabled=legacy_command_ingress_enabled,
            firebase_enabled=firebase_enabled,
            firebase_database_url=os.getenv(f"{prefix}FIREBASE_DATABASE_URL", "").strip(),
            firebase_service_account_json=os.getenv(
                f"{prefix}FIREBASE_SERVICE_ACCOUNT_JSON", ""
            ).strip(),
            greenhouse_id=os.getenv(f"{prefix}GREENHOUSE_ID", "g2").strip() or "g2",
            firebase_g1_state_path=(
                os.getenv(f"{prefix}FIREBASE_G1_STATE_PATH", "examples/greenhouse1/state").strip()
                or "examples/greenhouse1/state"
            ),
            firebase_g1_commands_pending_path=(
                os.getenv(
                    f"{prefix}FIREBASE_G1_COMMANDS_PENDING_PATH",
                    "examples/greenhouse1/commands/pending",
                ).strip()
                or "examples/greenhouse1/commands/pending"
            ),
            firebase_g1_commands_history_path=(
                os.getenv(
                    f"{prefix}FIREBASE_G1_COMMANDS_HISTORY_PATH",
                    "examples/greenhouse1/commands/history",
                ).strip()
                or "examples/greenhouse1/commands/history"
            ),
            firebase_g2_state_path=(
                os.getenv(f"{prefix}FIREBASE_G2_STATE_PATH", "examples/greenhouse2/state").strip()
                or "examples/greenhouse2/state"
            ),
            firebase_g2_commands_pending_path=(
                os.getenv(
                    f"{prefix}FIREBASE_G2_COMMANDS_PENDING_PATH",
                    "examples/greenhouse2/commands/pending",
                ).strip()
                or "examples/greenhouse2/commands/pending"
            ),
            firebase_g2_commands_history_path=(
                os.getenv(
                    f"{prefix}FIREBASE_G2_COMMANDS_HISTORY_PATH",
                    "examples/greenhouse2/commands/history",
                ).strip()
                or "examples/greenhouse2/commands/history"
            ),
            firebase_t3_state_path=(
                os.getenv(f"{prefix}FIREBASE_T3_STATE_PATH", "examples/temperature-node/state").strip()
                or "examples/temperature-node/state"
            ),
            firebase_processing_by=(
                os.getenv(
                    f"{prefix}FIREBASE_PROCESSING_BY",
                    "logline_greenhouse_edge",
                ).strip()
                or "logline_greenhouse_edge"
            ),
            firebase_poll_interval_sec=float(
                os.getenv(f"{prefix}POLL_INTERVAL_SEC", "1.0")
            ),
            firebase_command_expire_sec=int(
                os.getenv(f"{prefix}COMMAND_EXPIRE_SEC", "90")
            ),
            firebase_stale_state_sec=int(
                os.getenv(f"{prefix}STALE_STATE_SEC", "45")
            ),
            greenhouse1_status_poll_interval_sec=float(
                os.getenv(f"{prefix}GREENHOUSE1_STATUS_POLL_INTERVAL_SEC", "5.0")
            ),
            dry_run=cls._bool_env(os.getenv(f"{prefix}DRY_RUN", "1")),
        )

    @staticmethod
    def _require(prefix: str, suffix: str) -> str:
        env_name = f"{prefix}{suffix}"
        value = os.getenv(env_name, "").strip()
        if not value:
            raise RuntimeError(f"Missing required environment variable: {env_name}")
        return value

    @classmethod
    def _require_if(cls, prefix: str, suffix: str, required: bool) -> str:
        if required:
            return cls._require(prefix, suffix)
        return os.getenv(f"{prefix}{suffix}", "").strip()

    @staticmethod
    def _bool_env(raw: str) -> bool:
        return raw.strip().lower() not in {"0", "false", "no", "off"}
