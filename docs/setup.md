# Setup

Use a local Python environment first.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with local placeholder values. Do not commit `.env`.

Run the bridge:

```bash
./scripts/run_edge_bridge.sh
```

Run optional loggers:

```bash
./scripts/run_dualzone_logger.sh
./scripts/run_singlezone_logger.sh
```

The examples default to placeholder hostnames such as `http://greenhouse-device.local` and local-only bind host `127.0.0.1`.
