# Firebase command sync

## Problem

App-side command intent needs a controlled boundary before it reaches local devices.

## Hypothesis

A pending/history queue model can separate command intent, processing, and result tracking.

## Experiment

Keep Firebase-style paths generic and document the processing lifecycle without private project details.

The public export should validate this boundary with placeholders, mocks, or a non-production test backend before any live sync claim.

## Evidence status

Dry-run bridge configuration and Python tests passed in the sanitized export.

Disabled Firebase mode no longer requires private service-account values.

This confirms safe local configuration loading, not live Firebase sync behavior.

## Current result

- Dry-run config without Firebase credentials: PASS.
- Enabled integration secret validation: PASS for clear failure when required values are missing.
- Public-safe Firebase-style sync replay: NOT VALIDATED.
- Real Firebase project/service-account use: excluded from public export.

## Status

Draft / dry-run boundary verified / sync replay still needed.

## Trust level

Medium for configuration boundaries and secret handling.

Low-Medium for sync behavior until mocked or documented replay exists.

## Next question

Should the public version include a local fake sync backend for testing before any real Firebase-style integration is documented?
