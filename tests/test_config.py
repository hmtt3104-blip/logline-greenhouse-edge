from __future__ import annotations

import os
from pathlib import Path

import pytest

from greenhouse_bridge.config import BridgeConfig


PREFIX = "GREENHOUSE_BRIDGE_"


def _clear_bridge_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith(PREFIX):
            monkeypatch.delenv(key, raising=False)


def _load_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    env_example = Path(__file__).resolve().parents[1] / ".env.example"
    for line in env_example.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.startswith(PREFIX):
            monkeypatch.setenv(key, value)


def _set_minimum_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{PREFIX}MQTT_HOST", "MQTT_BROKER_HOST")
    monkeypatch.setenv(f"{PREFIX}MQTT_PORT", "1883")


def test_env_example_loads_with_disabled_integrations(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_bridge_env(monkeypatch)
    _load_env_example(monkeypatch)

    config = BridgeConfig.from_env()

    assert config.dry_run is True
    assert config.telegram_egress_enabled is False
    assert config.command_polling_enabled is False
    assert config.legacy_command_ingress_enabled is False
    assert config.firebase_enabled is False
    assert config.telegram_bot_token == ""
    assert config.telegram_chat_id == ""
    assert config.pi_to_app_key_b64 == ""
    assert config.app_to_pi_key_b64 == ""


def test_enabled_telegram_egress_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_bridge_env(monkeypatch)
    _set_minimum_required_env(monkeypatch)
    monkeypatch.setenv(f"{PREFIX}TELEGRAM_EGRESS_ENABLED", "1")

    with pytest.raises(RuntimeError, match=f"{PREFIX}TELEGRAM_BOT_TOKEN"):
        BridgeConfig.from_env()


def test_enabled_command_ingress_requires_crypto_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_bridge_env(monkeypatch)
    _set_minimum_required_env(monkeypatch)
    monkeypatch.setenv(f"{PREFIX}TELEGRAM_BOT_TOKEN", "placeholder-token")
    monkeypatch.setenv(f"{PREFIX}TELEGRAM_CHAT_ID", "placeholder-chat")
    monkeypatch.setenv(f"{PREFIX}LEGACY_COMMAND_INGRESS_ENABLED", "1")

    with pytest.raises(RuntimeError, match=f"{PREFIX}PI_TO_APP_KEY_B64"):
        BridgeConfig.from_env()
