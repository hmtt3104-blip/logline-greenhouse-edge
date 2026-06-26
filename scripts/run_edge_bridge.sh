#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$REPO_DIR/.env" ]]; then
  set -a
  source "$REPO_DIR/.env"
  set +a
fi

export PYTHONPATH="$REPO_DIR/edge${PYTHONPATH:+:$PYTHONPATH}"

if [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
  exec "$REPO_DIR/.venv/bin/python" -m greenhouse_bridge
fi

exec python3 -m greenhouse_bridge
