# Changelog

## Unreleased

### Added

- Created sanitized public export skeleton for Logline greenhouse edge experiments.
- Added public-readiness checklist result in `docs/safety.md`.
- Added Foundation-aligned status, safety, and roadmap language.
- Added a no-hardware synthetic integration test for `.env.example` config loading, direct state-store telemetry normalization, and localhost mock HTTP command dispatch.

### Changed

- Set public readiness to `NEEDS_CLEANUP` instead of claiming `READY` before validation evidence exists.
- Clarified that command dispatch, systemd examples, sanitized bridge imports, and draft experiment records still need validation.
- Documented the evidence required before the repository can be treated as `READY`.
- Changed bridge runtime defaults to a safer public posture: dry-run enabled, Telegram egress disabled, command polling disabled, and legacy command ingress disabled unless explicitly enabled.
- Changed logger default output directories to repo-local `data/dualzone-web-logs` and `data/singlezone-web-logs` generated-output locations.
- Allow public dry-run bridge configuration to load without Telegram tokens or crypto keys while optional integrations remain disabled.
- Updated bootstrap, MQTT, and Firebase experiment records to distinguish verified dry-run/import/config behavior from unvalidated live MQTT/Firebase/device behavior.
- Clarified that localhost mock HTTP command dispatch is validated, while real ESP command dispatch still needs non-production hardware validation before any live-device safety claim.
- Clarified architecture safety boundaries for conservative defaults and live-device dispatch review.
- Clarified that systemd service examples are placeholders and need non-private validation before production claims.

### Security

- Documented private topology, service-account JSON, Telegram tokens, runtime paths, generated logs, and deployment runbooks as excluded public content.
- Added `BLOCKED` escalation rules for secrets, private topology, generated outputs, and live deployment details.
