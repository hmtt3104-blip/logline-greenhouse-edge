# Raspberry bridge bootstrap

## Problem

The edge runtime needs one process that connects telemetry, command handling, and local device control.

## Hypothesis

A small Python bridge can coordinate MQTT, HTTP, and sync boundaries without hiding configuration.

## Experiment

Run the bridge configuration and imports from environment-driven config with local-only defaults and placeholder hosts.

## Environment

Repository: `logline-greenhouse-edge`

Python: 3.12.10

Local virtual environment: `.venv/` ignored by Git

Dependencies installed from `requirements.txt`:

- `cryptography`
- `paho-mqtt`
- `firebase-admin`

Config posture:

- dry-run enabled;
- Telegram egress disabled;
- command polling disabled;
- legacy command ingress disabled;
- Firebase disabled;
- direct control bound to `127.0.0.1`.

## Data

Validation performed from the sanitized export:

```text
PYTHONPATH=edge
python -m pytest
4 passed
```

Dry-run config loading with `.env.example` values: PASS.

Validation behavior:

- disabled optional integrations do not require private Telegram tokens or crypto keys;
- enabling Telegram egress without token/chat ID fails clearly;
- enabling legacy command ingress without required crypto key fails clearly.

## Results

Dry-run reproducibility: PASS.

Runtime/live integration behavior: NOT VALIDATED.

The sanitized export can import bridge modules and load safe dry-run configuration without private secrets.

## Status

Draft / dry-run validated / needs runtime integration validation.

## Trust level

Medium for dry-run configuration and import reproducibility.

Low for live MQTT/Firebase/device behavior until tested in a non-private environment.

## Remaining gaps

- live MQTT ingestion not validated in this public export;
- Firebase-style sync not validated with public-safe credentials/mock;
- HTTP command dispatch not validated against a mock or non-production target;
- systemd examples not validated on a clean Raspberry Pi;
- experiment records still need integration results before any `READY` claim.

## Next question

What is the smallest non-private local demo that validates MQTT ingestion and command-dispatch boundaries without touching live greenhouse devices?
