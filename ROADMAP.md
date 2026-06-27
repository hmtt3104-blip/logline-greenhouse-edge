# Roadmap

## Current status

Repository status: `Prototype`

Public readiness: `NEEDS_CLEANUP`

Production readiness: `Not production-ready`

Reason: this repository is a sanitized public Logline export, but sanitized bridge imports, command-dispatch behavior, systemd examples, draft experiment records, and reproducibility still need validation before this repository can be treated as `READY`.

## Near-term

- [x] Publish a sanitized public export without private runtime history.
- [x] Exclude private IP maps, private paths, private usernames, service-account JSON, tokens, generated logs, and runtime outputs.
- [x] Record the public-readiness checklist result in `docs/safety.md`.
- [ ] Validate sanitized bridge imports.
- [ ] Review logger defaults after sanitization.
- [ ] Expand setup and configuration docs.
- [ ] Add decision records for edge boundaries.
- [ ] Define the smallest non-private reproducible local test environment.

## Experiments to run

- [ ] MQTT telemetry ingestion using sanitized placeholder topics and local broker assumptions.
- [ ] Firebase-style sync boundary using placeholders only.
- [ ] HTTP command dispatch against a non-production target or mock.
- [ ] Logger behavior with sanitized output directories.
- [ ] Systemd supervision using generic paths and placeholder env files.

## Documentation to add

- [ ] Decision record for edge runtime public export boundary.
- [ ] Decision record for command dispatch safety boundary.
- [ ] Decision record for systemd supervision model.
- [ ] Repeatable setup notes for a non-private local test environment.
- [ ] Synthetic telemetry samples.

## Cleanup / review still required

- [ ] Confirm `.env`, service-account JSON, Telegram tokens, private IPs, live topology, generated logs, backups, and runtime outputs are absent before each major public update.
- [ ] Confirm all examples use placeholders and local-only defaults.
- [ ] Confirm command-dispatch examples cannot be mistaken for production-safe instructions.
- [ ] Confirm systemd examples do not include private users, paths, hosts, or deployment assumptions.

## Evidence required before `READY`

Public readiness should remain `NEEDS_CLEANUP` until:

- sanitized bridge imports are validated;
- logger defaults are reviewed after sanitization;
- command-dispatch behavior is tested against a non-production target or mock;
- systemd examples are validated with generic paths and placeholder env files;
- draft experiment records are updated against the sanitized export;
- the smallest non-private local test path is documented.

## Later

- Add small integration tests for config loading.
- Split optional integrations behind clearer adapters.
- Evaluate which edge-runtime components can become reusable templates.
