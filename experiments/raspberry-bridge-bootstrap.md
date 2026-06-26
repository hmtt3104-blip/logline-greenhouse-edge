# Raspberry bridge bootstrap

## Problem

The edge runtime needs one process that connects telemetry, command handling, and local device control.

## Hypothesis

A small Python bridge can coordinate MQTT, HTTP, and sync boundaries without hiding configuration.

## Experiment

Run the bridge from environment-driven config with local-only defaults and placeholder hosts.

## Status

Draft from sanitized export.

## Trust level

Medium. The shape comes from working runtime code, but the sanitized export still needs validation.

## Next question

Which minimum config values should be required for a reproducible local demo?
