# logline-greenhouse-edge

Raspberry Pi edge runtime experiments for greenhouse climate telemetry, MQTT ingestion, Firebase-style sync, HTTP control dispatch, and systemd supervision.

Status: `Prototype / sanitized public export`

## What this is

This repository is a public Logline experiment around a Raspberry Pi edge runtime for greenhouse automation. It explores how a small local process can collect telemetry, normalize state, dispatch guarded control commands, and supervise helper loggers.

## Problem

Small greenhouse systems often grow from separate scripts: telemetry readers, command bridges, local loggers, and service wrappers. The hard part is making the edge layer understandable, observable, and repeatable without exposing private runtime details.

## Hypothesis

A Raspberry Pi can act as a clear edge boundary when configuration, device mapping, command dispatch, and runtime supervision are documented separately from private environment values.

## Experiment

The export contains a sanitized bridge package, logger scripts, example mappings, run wrappers, and systemd examples. It keeps the engineering shape while replacing private hosts, paths, and environment values with public placeholders.

## Architecture

```text
MQTT telemetry
  -> edge bridge
  -> normalized state store
  -> Firebase-style sync boundary
  -> guarded HTTP command dispatch

Device HTTP status
  -> logger scripts
  -> local JSON/log outputs
  -> optional summaries

systemd examples
  -> edge bridge and logger supervision
```

See `docs/architecture.md`.

## Current status

- Bridge and logger code are imported from a private working/runtime repository.
- Private IPs, local usernames, private paths, runtime maps, and generated outputs are excluded or rewritten.
- The experiment records are drafts and need validation against the sanitized export.

## Safety notes

- Do not commit `.env`.
- Do not commit service-account JSON files.
- Do not commit Telegram tokens.
- Keep HTTP control endpoints local unless deliberately isolated.
- Treat device addresses, greenhouse topology, and runtime paths as private.

See `docs/safety.md` and `SECURITY.md`.

## Repository map

```text
edge/              Bridge package
loggers/           Device status loggers and summary tools
scripts/           Local run wrappers and diagnostics
systemd/           Example service units
examples/          Sanitized mapping and env examples
docs/              Architecture, setup, configuration, deployment, safety
experiments/       Logline experiment records
data/              Notes for local generated data
reference/         Notes for private runtime references
tests/             Unit tests copied from the bridge source
```

## How to run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./scripts/run_edge_bridge.sh
```

Use placeholder hosts first, then replace values only in local `.env`.
