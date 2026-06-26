# Deployment Notes

This document describes sanitized service patterns for a Raspberry Pi edge experiment.

## Service examples

Example units live in `systemd/`:

- `logline-greenhouse-edge.service.example`
- `logline-dualzone-logger.service.example`
- `logline-singlezone-logger.service.example`

They use `/opt/logline-greenhouse-edge` and user `logline` as placeholders.

## Local generated data

Logger outputs should go under a local data directory and stay ignored by Git:

- `latest-status.json`
- `state.json`
- `*.ndjson`
- `*.log`

## Advanced binding

Binding a control endpoint to `0.0.0.0` exposes it beyond loopback. Keep public examples on `127.0.0.1` unless a separate network review is done.
