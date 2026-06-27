# Security Policy

## Current status

Repository status: Prototype.

Public readiness: NEEDS_CLEANUP.

Production readiness: Not production-ready.

This repository is a sanitized public Logline export. The private working/runtime repository is maintained separately and is not part of this public history.

## What must not be committed

Never commit:

- `.env` files;
- Telegram tokens;
- service-account JSON;
- private keys;
- private device addresses;
- private IP maps;
- live greenhouse topology;
- private usernames or home paths;
- deployment runbooks from real systems;
- generated runtime logs;
- state files, backups, or summaries;
- binaries or images from real deployments.

## Runtime configuration

Use placeholders in public examples.

Keep real values only in local `.env` or other ignored local runtime files.

Do not paste private hostnames, local absolute paths, device URLs, VPN details, Firebase/service-account values, or Telegram settings into public issues, pull requests, comments, or documentation.

## Control endpoint boundary

HTTP command dispatch examples are for sanitized review only.

Do not treat them as production-safe until target devices, network exposure, authentication or isolation, command limits, and failure behavior are documented and reviewed.

## Status escalation

If a secret, service-account JSON, token, private IP, live topology, private runtime path, generated log, or deployment runbook is found in this repository, public readiness becomes `BLOCKED` until the unsafe content is removed and any exposed credential is rotated.

If command-dispatch safety is uncertain, public readiness remains `NEEDS_CLEANUP`.

## Reporting security issues

Do not report sensitive values by pasting them into issues or pull requests.

Report the type of issue and affected file path without repeating the secret value.

If a secret is exposed, rotate it outside this repository before continuing public work.
