# Changelog

## Unreleased

### Added

- Created sanitized public export skeleton for Logline greenhouse edge experiments.
- Added public-readiness checklist result in `docs/safety.md`.
- Added Foundation-aligned status, safety, and roadmap language.

### Changed

- Set public readiness to `NEEDS_CLEANUP` instead of claiming `READY` before validation evidence exists.
- Clarified that command dispatch, systemd examples, sanitized bridge imports, and draft experiment records still need validation.
- Documented the evidence required before the repository can be treated as `READY`.
- Changed bridge runtime defaults to a safer public posture: dry-run enabled, Telegram egress disabled, command polling disabled, and legacy command ingress disabled unless explicitly enabled.
- Changed logger default output directories to repo-local `data/dualzone-web-logs` and `data/singlezone-web-logs` generated-output locations.

### Security

- Documented private topology, service-account JSON, Telegram tokens, runtime paths, generated logs, and deployment runbooks as excluded public content.
- Added `BLOCKED` escalation rules for secrets, private topology, generated outputs, and live deployment details.
