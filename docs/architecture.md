# Architecture

This export models a Raspberry Pi edge runtime for greenhouse experiments.

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
- Command dispatch passes through mapping and guard layers.
- Logger outputs are local generated data and are not committed.

## Main modules

- `edge/greenhouse_bridge/config.py` loads edge configuration.
- `edge/greenhouse_bridge/state_store.py` stores normalized greenhouse state.
- `edge/greenhouse_bridge/mqtt_bridge.py` reads telemetry topics.
- `edge/greenhouse_bridge/firebase_sync.py` models app/cloud sync boundaries.
- `edge/greenhouse_bridge/controller_http.py` dispatches normalized commands to device HTTP endpoints.
- `loggers/` contains status loggers and summary tools.
