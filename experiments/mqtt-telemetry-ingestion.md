# MQTT telemetry ingestion

## Problem

Device telemetry needs to become a stable greenhouse state model.

## Hypothesis

Topic mapping plus a state store can normalize telemetry without coupling the app to device-specific topics.

## Experiment

Use sanitized MQTT mapping examples and bridge state handling tests.

The public export should validate telemetry ingestion with synthetic MQTT messages or a local broker before any live greenhouse topic claim.

## Evidence status

Dry-run bridge configuration and Python tests passed in the sanitized export.

No-hardware pytest updates the state store directly with synthetic `greenhouse/example/...` telemetry topics.

This confirms that the bridge package can import and load safe local configuration without private secrets.

It does not confirm live MQTT broker ingestion behavior.

## Current result

- Bridge import/config baseline: PASS.
- Direct synthetic telemetry normalization: PASS.
- Public-safe live MQTT broker replay: NOT VALIDATED.
- Real greenhouse MQTT topics: excluded from public export.

## Status

Draft / dry-run baseline verified / direct synthetic telemetry verified / MQTT broker replay still needed.

## Trust level

Medium for repository shape, configuration boundary, state-store testability, and direct synthetic telemetry normalization.

Low for live MQTT ingestion until validated with synthetic messages or a non-private local broker.

## Next question

What minimal synthetic MQTT message set is needed for a public reproducibility test without exposing live greenhouse topics?
