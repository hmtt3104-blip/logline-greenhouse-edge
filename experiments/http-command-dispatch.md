# HTTP command dispatch

## Problem

Simple device HTTP control routes need guardrails and normalized command mapping.

## Hypothesis

A command guard plus explicit mapping table reduces accidental unsafe dispatch.

## Experiment

Use sanitized HTTP control mapping examples with placeholder device hosts.

The public export should test command dispatch only against a mock, placeholder, or non-production target.

It must not be treated as safe for live greenhouse device control until target devices, command limits, network exposure, authentication or isolation, timeout behavior, and failure behavior are documented and reviewed.

## Evidence status

- Placeholder mapping exists.
- Public-safe live-device evidence does not exist in this export.
- Non-production dispatch replay or mock testing still needs to be documented.

## Status

Draft from sanitized export.

Public readiness impact: keeps repository at `NEEDS_CLEANUP` until dispatch behavior is validated safely.

## Trust level

Low-Medium. The public shape is useful, but production safety is not proven.

## Next question

Which commands should remain in the public mapping examples, and which should require a private deployment-specific review?
