# Configuration

Configuration is environment-driven.

Use `.env.example` as the public template and keep real `.env` files local only.

## Required local values

For local testing, use placeholders first:

- `GREENHOUSE_BRIDGE_MQTT_HOST`
- `GREENHOUSE_BRIDGE_MQTT_PORT`
- `GREENHOUSE_BRIDGE_GREENHOUSE1_BASE_URL`
- `GREENHOUSE_BRIDGE_GREENHOUSE2_BASE_URL`

Do not publish real broker hosts, device URLs, private IPs, VPN details, or greenhouse topology.

## Safe default posture

The public example is expected to start in a non-production posture:

- `GREENHOUSE_BRIDGE_DRY_RUN=1`
- `GREENHOUSE_BRIDGE_COMMAND_POLLING_ENABLED=0`
- `GREENHOUSE_BRIDGE_LEGACY_COMMAND_INGRESS_ENABLED=0`
- `GREENHOUSE_BRIDGE_FIREBASE_ENABLED=0`
- `GREENHOUSE_BRIDGE_TELEGRAM_EGRESS_ENABLED=0`
- `GREENHOUSE_BRIDGE_DIRECT_CONTROL_HOST=127.0.0.1`

Changing these values may move the experiment closer to live control or external egress and should be reviewed before use.

With these defaults, `BridgeConfig.from_env()` must load without Telegram tokens, service-account JSON, or crypto keys.

## Optional integrations

- Telegram egress can be disabled with `GREENHOUSE_BRIDGE_TELEGRAM_EGRESS_ENABLED=0`.
- Firebase-style sync can be disabled with `GREENHOUSE_BRIDGE_FIREBASE_ENABLED=0`.
- Direct HTTP control should bind to `127.0.0.1` in examples.

Telegram token and chat ID are required when Telegram egress, Telegram command polling, or legacy command ingress is enabled.

App-layer crypto keys are required when encrypted Telegram egress or legacy command ingress features are enabled. They are intentionally not required for the public dry-run posture where those features are disabled.

## Service-account values

Do not commit service-account JSON.

If Firebase-style sync is tested, keep the service account outside Git and point to it only from a local ignored `.env`.

## Example paths

Use `/path/to/logline-greenhouse-edge/...` in service examples. Local development may use any uncommitted path outside the repository.

Do not publish private usernames, home directories, runtime maps, generated logs, or service runbooks from a real deployment.
