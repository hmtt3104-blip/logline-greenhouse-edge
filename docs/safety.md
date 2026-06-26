# Safety

This repository is a sanitized public Logline export. The private working/runtime repository is maintained separately.

## Public export boundaries

Excluded from this export:

- private IP map;
- private usernames and home paths;
- runtime maps and service runbooks;
- `.env` files;
- service-account JSON;
- Telegram tokens;
- generated logs and runtime outputs;
- images and binaries.

## Control endpoint exposure

Examples use `127.0.0.1` for local-only binding. Binding to `0.0.0.0` is an advanced mode and should be reviewed before use.

## Config handling

Use `.env.example` as a template. Keep real values in local `.env` only.

## Generated data

Do not commit status logs, snapshots, summaries, or local state files.
