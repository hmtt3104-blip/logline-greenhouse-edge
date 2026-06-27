# logline-greenhouse-edge

Raspberry Pi edge runtime experiments for greenhouse climate telemetry, MQTT ingestion, Firebase-style sync, HTTP dispatch, and systemd supervision.

## What this is

`logline-greenhouse-edge` is a sanitized public Logline export for exploring a Raspberry Pi edge runtime in greenhouse automation.

It documents how a small local process can collect telemetry, normalize state, dispatch guarded control commands, supervise helper loggers, and stay separate from private runtime configuration.

## Foundation

This repository follows the public standards and operating model defined in:

https://github.com/hmtt3104-blip/logline-foundation

Logline Foundation defines how public experiments are documented, reviewed, sanitized, and linked across repositories.

## Problem

Small greenhouse systems often grow from separate scripts: telemetry readers, command bridges, local loggers, and service wrappers.

The hard part is making the edge layer understandable, observable, and repeatable without exposing private runtime details.

## Hypothesis

A Raspberry Pi can act as a clear edge boundary when configuration, device mapping, command dispatch, and runtime supervision are documented separately from private environment values.

## Experiment

The export contains a sanitized bridge package, logger scripts, example mappings, run wrappers, tests, and systemd examples.

It preserves the engineering shape of the edge runtime while replacing private hosts, usernames, paths, runtime maps, logs, and environment values with public placeholders.

What is intentionally not treated as proven in this export:

- safe use against live greenhouse devices;
- production Firebase/service-account configuration;
- production command-dispatch safety;
- complete validation of sanitized systemd examples;
- complete validation of draft experiment records.

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

Repository status: `Prototype`

Public readiness: `NEEDS_CLEANUP`

Trust level: `Medium for documentation shape and safe defaults; low for production safety and sanitized runtime validation`

Production readiness: `Not production-ready`

Reason for public readiness status:

- The export is sanitized and excludes private IPs, private usernames, private paths, runtime maps, generated outputs, and deployment secrets.
- Public-readiness checklist result is recorded in `docs/safety.md` as `NEEDS_CLEANUP`.
- Bridge runtime defaults now use a safer public posture: dry-run enabled, Telegram egress disabled, command polling disabled, and legacy command ingress disabled unless explicitly enabled.
- Logger default outputs use repo-local generated-output directories under `data/`.
- Experiment records are draft-level and need validation against the sanitized export.
- Sanitized examples need validation on a non-private test environment.
- This repository should not be treated as pinned, flagship-ready, release-ready, or public-readiness `READY` until Foundation gate evidence exists.

Current boundaries:

- Bridge and logger code are imported from a private working/runtime repository.
- Private IPs, local usernames, private paths, runtime maps, and generated outputs are excluded or rewritten.
- Device mappings are examples only; real greenhouse topology stays private.
- This repository is not a production deployment package.

## Results / Lessons

- A Raspberry Pi edge layer is a useful boundary between greenhouse devices, telemetry, and higher-level interfaces.
- Config templates are safer than publishing real runtime values.
- Systemd examples are useful, but must remain generic and placeholder-based.
- Local loggers should be documented as helpers, not as hidden production runbooks.
- Clean export is safer than publishing a working runtime repository with old operational history.

## What failed / remains incomplete

- Experiment records are still draft-level.
- Sanitized examples need validation on a non-private test environment.
- The Firebase-style sync boundary is documented, but not presented as a real public service setup.
- Device mappings are examples only; real greenhouse topology stays private.
- Release status is not ready yet.

## Next questions

- Which edge-runtime components are reusable as generic templates?
- Which parts should stay greenhouse-specific?
- What is the smallest reproducible local test environment?
- Should command dispatch be documented as a separate decision record?
- Which logger behavior should be promoted to a repeatable experiment?

## Safety / Security notes

- Do not commit `.env`.
- Do not commit service-account JSON files.
- Do not commit Telegram tokens.
- Keep HTTP control endpoints local unless deliberately isolated.
- Treat device addresses, greenhouse topology, private usernames, and runtime paths as private.
- Do not publish generated logs, state files, backups, or runtime outputs.

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

## Related experiments

- `experiments/raspberry-bridge-bootstrap.md`
- `experiments/mqtt-telemetry-ingestion.md`
- `experiments/firebase-command-sync.md`
- `experiments/http-command-dispatch.md`
- `experiments/systemd-runtime-supervision.md`

## Related decision records

No accepted decision records yet.

Planned candidates:

- edge runtime public export boundary;
- command dispatch safety boundary;
- systemd supervision model.

## Related repositories

- `logline-foundation`: public standards and operating model for Logline.
- `logline-greenhouse-firmware`: sanitized ESP32-S3 dual-zone greenhouse firmware experiment.
- `logline-greenhouse-ai`: Raspberry Pi greenhouse climate monitoring and computer vision prototype.
