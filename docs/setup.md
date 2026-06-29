# Setup

Use a local Python environment first.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with local placeholder values. Do not commit `.env`.

Recommended first-run defaults:

```text
GREENHOUSE_BRIDGE_DRY_RUN=1
GREENHOUSE_BRIDGE_COMMAND_POLLING_ENABLED=0
GREENHOUSE_BRIDGE_LEGACY_COMMAND_INGRESS_ENABLED=0
GREENHOUSE_BRIDGE_FIREBASE_ENABLED=0
GREENHOUSE_BRIDGE_TELEGRAM_EGRESS_ENABLED=0
GREENHOUSE_BRIDGE_DIRECT_CONTROL_HOST=127.0.0.1
```

These defaults keep the export in a local, non-production test posture.

Validate configuration loading before starting any runtime process:

```bash
PYTHONPATH=edge python -c "from greenhouse_bridge.config import BridgeConfig; BridgeConfig.from_env(); print('config OK')"
```

Do not replace placeholder hosts with live greenhouse device URLs until command-dispatch safety, network exposure, and failure behavior are reviewed.

Run the bridge only after replacing placeholders with non-private local test endpoints or mocks:

```bash
./scripts/run_edge_bridge.sh
```

Run optional loggers:

```bash
./scripts/run_dualzone_logger.sh
./scripts/run_singlezone_logger.sh
```

The examples default to placeholder hostnames such as `http://greenhouse-device.local` and local-only bind host `127.0.0.1`.

Logger outputs and generated state files must stay local and ignored by Git.
