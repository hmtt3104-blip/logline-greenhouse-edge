# systemd runtime supervision

## Problem

Edge processes need predictable startup, restart, and log boundaries on Raspberry Pi.

## Hypothesis

Small systemd units can supervise the bridge and loggers without embedding private paths.

## Experiment

Provide sanitized service examples using `/path/to/logline-greenhouse-edge` and user `logline`.

The public examples are placeholders. They must be adapted only in private local copies, and real usernames, paths, hostnames, service-account paths, and runtime maps must not be committed.

## Evidence status

- Sanitized service examples exist.
- Public examples use placeholder paths and user names.
- Validation on a non-private Raspberry Pi test environment is not documented yet.
- Production service behavior is not proven in this export.

## Status

Draft from sanitized export.

Public readiness impact: keeps repository at `NEEDS_CLEANUP` until systemd examples are validated with generic paths and placeholder env files.

## Trust level

Low-Medium. The supervision model is useful, but the sanitized examples still need non-private validation.

## Next question

Should service files stay examples or become installable templates after validation?
