# Configuration

Configuration is environment-driven.

## Required local values

- `GREENHOUSE_BRIDGE_MQTT_HOST`
- `GREENHOUSE_BRIDGE_MQTT_PORT`
- `GREENHOUSE_BRIDGE_GREENHOUSE1_BASE_URL`
- `GREENHOUSE_BRIDGE_GREENHOUSE2_BASE_URL`

## Optional integrations

- Telegram egress can be disabled with `GREENHOUSE_BRIDGE_TELEGRAM_EGRESS_ENABLED=0`.
- Firebase-style sync can be disabled with `GREENHOUSE_BRIDGE_FIREBASE_ENABLED=0`.
- Direct HTTP control should bind to `127.0.0.1` in examples.

## Example paths

Use `/path/to/logline-greenhouse-edge/...` in service examples. Local development may use any uncommitted path outside the repository.
