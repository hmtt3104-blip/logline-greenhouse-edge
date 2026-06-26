# systemd runtime supervision

## Problem

Edge processes need predictable startup, restart, and log boundaries on Raspberry Pi.

## Hypothesis

Small systemd units can supervise the bridge and loggers without embedding private paths.

## Experiment

Provide sanitized service examples using `/opt/logline-greenhouse-edge` and user `logline`.

## Status

Draft from sanitized export.

## Trust level

Medium.

## Next question

Should service files stay examples or become installable templates?
