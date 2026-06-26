from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def duration_ms(start: float, end: float | None = None) -> int:
    finished = monotonic() if end is None else end
    return max(0, int(round((finished - start) * 1000)))


class JsonlPerformanceLogger:
    """Best-effort JSONL logger that must never break greenhouse runtime."""

    def __init__(self, path: str | Path | None = None) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        self.path = Path(path) if path is not None else base_dir / "logs" / "performance.log"
        self._lock = Lock()

    def log_event(self, event: str, **fields: Any) -> None:
        payload = {
            "timestamp": utc_now_iso(),
            "event": event,
        }
        for key, value in fields.items():
            if value is not None:
                payload[key] = value

        try:
            raw = json.dumps(payload, ensure_ascii=False)
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(raw)
                    handle.write("\n")
        except Exception:
            return


_DEFAULT_LOGGER = JsonlPerformanceLogger()


def get_performance_logger() -> JsonlPerformanceLogger:
    return _DEFAULT_LOGGER
