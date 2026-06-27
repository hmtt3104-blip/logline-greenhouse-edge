# Safety

Repository status: Prototype.

Public readiness: NEEDS_CLEANUP.

Production readiness: Not production-ready.

This repository is a sanitized public Logline export. The private working/runtime repository is maintained separately and is not part of this public history.

The repository remains `NEEDS_CLEANUP` until experiment records, sanitized examples, command-dispatch safety, systemd examples, and public-readiness checklist evidence are reviewed against the sanitized export.

## Public readiness checklist result

Final public readiness status: NEEDS_CLEANUP.

Reason:

- The public tree is sanitized and excludes private IP maps, private usernames, private paths, `.env` files, service-account JSON, Telegram tokens, generated logs, runtime outputs, images, and binaries.
- Device mappings are examples only and do not document real greenhouse topology.
- HTTP command dispatch and service supervision examples still need validation in a non-private test environment.
- Experiment records are draft-level and need review against the sanitized export.

Finding statuses:

| Area | Finding status | Notes |
| --- | --- | --- |
| Secrets and tokens | OK | `.env`, service-account JSON, Telegram tokens, and private keys are excluded. |
| Private topology | OK | Real device maps, private IPs, usernames, and runtime paths are excluded or rewritten. |
| Generated outputs | OK | Runtime logs, state files, backups, and generated outputs are excluded. |
| Command dispatch | WARNING | Examples are sanitized, but live-device safety is not validated in this public export. |
| Systemd supervision | WARNING | Example units are generic and need validation outside private runtime assumptions. |
| Experiment records | WARNING | Records are draft-level and need validation against the sanitized export. |
| Reproducibility | WARNING | A smallest non-private local test environment is not fully documented yet. |

## Public export boundaries

Excluded from this export:

- private IP map;
- private usernames and home paths;
- runtime maps and service runbooks;
- `.env` files;
- service-account JSON;
- Telegram tokens;
- generated logs and runtime outputs;
- images and binaries.

## Control endpoint exposure

Examples use `127.0.0.1` for local-only binding. Binding to `0.0.0.0` is an advanced mode and should be reviewed before use.

HTTP command dispatch against live devices must not be treated as production-safe until command boundaries, target devices, authentication/network controls, and failure behavior are documented and reviewed.

## Config handling

Use `.env.example` as a template. Keep real values in local `.env` only.

Do not paste real hostnames, private IPs, service credentials, Telegram values, or local filesystem paths into public documentation.

## Generated data

Do not commit status logs, snapshots, summaries, local state files, backups, or runtime outputs.

## Status escalation

If this repository contains a secret, token, service-account JSON, private IP map, live device topology, private runtime path, generated log, or deployment runbook, public readiness becomes `BLOCKED` until cleaned and reviewed.

If command-dispatch safety is uncertain, public readiness remains `NEEDS_CLEANUP`.

## Before pinned, flagship, or READY use

Do not treat this repository as pinned, flagship-ready, release-ready, or public-readiness `READY` until the checklist result and supporting evidence are documented and the remaining WARNING items are resolved or explicitly accepted with a documented reason.
