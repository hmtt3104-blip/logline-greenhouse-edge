#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_day_stamp(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time()).strftime("%Y-%m-%d")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.write("\n")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return default


def env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def env_float(name: str, default: float) -> float:
    try:
        return float(env_str(name, str(default)))
    except ValueError:
        return default


@dataclass
class Config:
    base_url: str
    out_dir: Path
    status_interval_sec: float
    timeout_sec: float


def load_config() -> Config:
    return Config(
        base_url=env_str("SINGLEZONE_LOGGER_BASE_URL", "http://greenhouse-device.local").rstrip("/"),
        out_dir=Path(env_str("SINGLEZONE_LOGGER_OUT_DIR", "/path/to/logline-greenhouse-edge/data/singlezone-web-logs")),
        status_interval_sec=env_float("SINGLEZONE_LOGGER_STATUS_INTERVAL_SEC", 5.0),
        timeout_sec=env_float("SINGLEZONE_LOGGER_TIMEOUT_SEC", 8.0),
    )


def fetch_json(url: str, timeout_sec: float) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def print_log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


class LoggerState:
    def __init__(self, path: Path) -> None:
        self.path = path
        raw = read_json(
            path,
            {
                "last_status": {},
                "last_transition_snapshot": {},
                "consecutive_failures": 0,
                "last_fetch_ok": True,
            },
        )
        self.last_status = raw.get("last_status", {}) if isinstance(raw.get("last_status"), dict) else {}
        self.last_transition_snapshot = (
            raw.get("last_transition_snapshot", {})
            if isinstance(raw.get("last_transition_snapshot"), dict)
            else {}
        )
        self.consecutive_failures = int(raw.get("consecutive_failures", 0))
        self.last_fetch_ok = bool(raw.get("last_fetch_ok", True))

    def save(self) -> None:
        write_json(
            self.path,
            {
                "last_status": self.last_status,
                "last_transition_snapshot": self.last_transition_snapshot,
                "consecutive_failures": self.consecutive_failures,
                "last_fetch_ok": self.last_fetch_ok,
            },
        )


def status_daily_path(out_dir: Path) -> Path:
    return out_dir / f"status-{local_day_stamp()}.ndjson"


def events_daily_path(out_dir: Path) -> Path:
    return out_dir / f"events-{local_day_stamp()}.log"


def transitions_daily_path(out_dir: Path) -> Path:
    return out_dir / f"transitions-{local_day_stamp()}.log"


def append_status_snapshot(out_dir: Path, status: dict[str, Any], base_url: str) -> None:
    record = {
        "loggedAt": utc_now_iso(),
        "source": base_url,
        **status,
    }
    append_line(status_daily_path(out_dir), json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    write_json(out_dir / "latest-status.json", record)


def transition_snapshot(status: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "mode",
        "state",
        "temp",
        "hum",
        "level",
        "close",
        "message",
        "routerStatus",
        "routerUrl",
        "wifiDisconnectReason",
        "sensorStatus",
        "rtcStatus",
        "sdStatus",
        "logStatus",
        "sensorErrors",
        "tempRaw",
        "timeNow",
    ]
    return {key: status.get(key) for key in keys}


def append_transition_log(out_dir: Path, state: LoggerState, status: dict[str, Any]) -> int:
    previous = state.last_transition_snapshot
    current = transition_snapshot(status)
    changes: list[str] = []

    for key, current_value in current.items():
        previous_value = previous.get(key)
        if previous_value != current_value:
            changes.append(f"{key}: {previous_value!r} -> {current_value!r}")

    if not changes:
        return 0

    append_line(
        transitions_daily_path(out_dir),
        f"[{utc_now_iso()}] " + " | ".join(changes),
    )
    state.last_transition_snapshot = current
    return len(changes)


def append_event(out_dir: Path, message: str) -> None:
    append_line(events_daily_path(out_dir), f"[{utc_now_iso()}] {message}")


def main() -> int:
    cfg = load_config()
    ensure_dir(cfg.out_dir)
    state = LoggerState(cfg.out_dir / "state.json")

    status_url = f"{cfg.base_url}/status"
    print_log(f"Single-zone logger started. base_url={cfg.base_url} out_dir={cfg.out_dir}")
    append_event(cfg.out_dir, f"logger started base_url={cfg.base_url}")

    next_status_at = 0.0

    while True:
        now = time.time()

        if now >= next_status_at:
            try:
                status = fetch_json(status_url, cfg.timeout_sec)
                append_status_snapshot(cfg.out_dir, status, cfg.base_url)
                append_transition_log(cfg.out_dir, state, status)
                if not state.last_fetch_ok and state.consecutive_failures:
                    append_event(cfg.out_dir, f"STATUS fetch recovered after {state.consecutive_failures} failure(s)")
                state.last_status = status
                state.last_fetch_ok = True
                state.consecutive_failures = 0
                state.save()
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                state.consecutive_failures += 1
                state.last_fetch_ok = False
                message = f"STATUS fetch failed: {exc}"
                append_event(cfg.out_dir, message)
                print_log(message)
                state.save()
            next_status_at = now + cfg.status_interval_sec

        time.sleep(0.25)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print_log("Single-zone logger stopped by keyboard interrupt")
        raise SystemExit(0)
