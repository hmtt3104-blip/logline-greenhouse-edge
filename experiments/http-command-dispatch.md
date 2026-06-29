# HTTP command dispatch

## Problem

Simple device HTTP control routes need guardrails and normalized command mapping.

## Hypothesis

A command guard plus explicit mapping table reduces accidental unsafe dispatch.

## Experiment

Use sanitized HTTP control mapping examples with placeholder device hosts and a localhost mock control endpoint.

The public export should test command dispatch only against a mock, placeholder, or non-production target.

It must not be treated as safe for live greenhouse device control until target devices, command limits, network exposure, authentication or isolation, timeout behavior, and failure behavior are documented and reviewed.

## Evidence status

- Placeholder mapping exists.
- No-hardware pytest dispatches a synthetic `g2.stop` command to a localhost mock `/control` endpoint.
- The test asserts the target URL stays on `127.0.0.1` and the firmware command body is `cmd=stop`.
- Public-safe live-device evidence does not exist in this export.
- Real ESP command dispatch still needs non-production hardware validation.

## Current result

- Localhost mock HTTP command dispatch: PASS.
- Real ESP command dispatch: NOT VALIDATED.
- Live greenhouse command safety: NOT VALIDATED.

## Status

Draft / localhost mock validated / needs non-production hardware validation.

Public readiness impact: keeps repository at `NEEDS_CLEANUP` until real device boundaries, authentication/isolation, and failure behavior are validated safely.

## Trust level

Medium for command mapping and localhost mock dispatch.

Low for real ESP or production safety until tested outside live greenhouse systems.

## Next question

Which commands should remain in the public mapping examples, and which should require a private deployment-specific review?
