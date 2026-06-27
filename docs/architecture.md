# Architecture

This export models a Raspberry Pi edge runtime for greenhouse experiments.

It documents the public shape of the edge layer, not a production deployment guarantee.

## Flow

```text
MQTT broker
  -> greenhouse_bridge.mqtt_bridge
  -> StateStore
  -> Firebase-style sync boundary
  -> command queue processing
  -> guarded HTTP control dispatch

Device status endpoints
  -> dual-zone / single-zone logger
  -> local status and transition files
  -> summary scripts
```

## Boundaries

- Configuration comes from environment variables.
- Device addresses are placeholders in public examples.
- Bridge defaults are conservative for public testing: dry-run enabled, command polling disabled, legacy command ingress disabled, Firebase disabled, Telegram egress disabled, and direct control bound to `127.0.0.1`.
- Command dispatch passes through mapping and guard layers, but production safety is not proven in this public export.
- Live-device dispatch requires separate review of target devices, command limits, network exposure, authentication or isolation, timeout behavior, and failure behavior.
- Logger outputs are local generated data and are not committed.

## Main modules

- `edge/greenhouse_bridge/config.py` loads edge configuration.
- `edge/greenhouse_bridge/state_store.py` stores normalized greenhouse state.
- `edge/greenhouse_bridge/mqtt_bridge.py` reads telemetry topics.
- `edge/greenhouse_bridge/firebase_sync.py` models app/cloud sync boundaries.
- `edge/greenhouse_bridge/controller_http.py` dispatches normalized commands to device HTTP endpoints.
- `loggers/` contains status loggers and summary tools.
