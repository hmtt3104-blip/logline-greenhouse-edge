# Deployment Notes

This document describes sanitized service patterns for a Raspberry Pi edge experiment.

This is not a production deployment runbook.

## Service examples

Example units live in `systemd/`:

- `logline-greenhouse-edge.service.example`
- `logline-dualzone-logger.service.example`
- `logline-singlezone-logger.service.example`

They use `/path/to/logline-greenhouse-edge` and user `logline` as placeholders.

Before adapting them, replace placeholders only in a private local copy and keep real usernames, paths, hostnames, service-account files, and runtime maps out of Git.

## Local generated data

Logger outputs should go under a local data directory and stay ignored by Git:

- `latest-status.json`
- `state.json`
- `*.ndjson`
- `*.log`

The public logger defaults use repo-local generated-output directories under `data/`. Generated files must remain local and ignored.

## Safe runtime posture

For first deployment tests, keep:

```text
GREENHOUSE_BRIDGE_DRY_RUN=1
GREENHOUSE_BRIDGE_COMMAND_POLLING_ENABLED=0
GREENHOUSE_BRIDGE_LEGACY_COMMAND_INGRESS_ENABLED=0
GREENHOUSE_BRIDGE_FIREBASE_ENABLED=0
GREENHOUSE_BRIDGE_TELEGRAM_EGRESS_ENABLED=0
GREENHOUSE_BRIDGE_DIRECT_CONTROL_HOST=127.0.0.1
```

Do not connect this export to live device command dispatch until the target, command limits, network exposure, authentication or isolation, and failure behavior are reviewed.

## Advanced binding

Binding a control endpoint to `0.0.0.0` exposes it beyond loopback. Keep public examples on `127.0.0.1` unless a separate network review is done.
