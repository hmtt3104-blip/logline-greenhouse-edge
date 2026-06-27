#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def env_int(name: str, default: int) -> int:
    try:
        return int(env_str(name, str(default)))
    except ValueError:
        return default


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
    events_interval_sec: float
    timeout_sec: float
    events_limit: int


def load_config() -> Config:
    default_out_dir = project_root() / "data" / "dualzone-web-logs"
    return Config(
        base_url=env_str("DUALZONE_LOGGER_BASE_URL", "http://greenhouse-device.local").rstrip("/"),
        out_dir=Path(env_str("DUALZONE_LOGGER_OUT_DIR", str(default_out_dir))),
        status_interval_sec=env_float("DUALZONE_LOGGER_STATUS_INTERVAL_SEC", 5.0),
        events_interval_sec=env_float("DUALZONE_LOGGER_EVENTS_INTERVAL_SEC", 2.0),
        timeout_sec=env_float("DUALZONE_LOGGER_TIMEOUT_SEC", 8.0),
        events_limit=env_int("DUALZONE_LOGGER_EVENTS_LIMIT", 200),
    )


def fetch_json(url: str, timeout_sec: float) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str, timeout_sec: float) -> str:
    with urlopen(url, timeout=timeout_sec) as response:
        return response.read().decode("utf-8", errors="replace")


def print_log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


class LoggerState:
    def __init__(self, path: Path) -> None:
        self.path = path
        raw = read_json(
            path,
            {
                "last_event_seq": 0,
                "last_status": {},
                "last_transition_snapshot": {},
            },
        )
        self.last_event_seq = int(raw.get("last_event_seq", 0))
        self.last_status = raw.get("last_status", {}) if isinstance(raw.get("last_status"), dict) else {}
        self.last_transition_snapshot = (
            raw.get("last_transition_snapshot", {})
            if isinstance(raw.get("last_transition_snapshot"), dict)
            else {}
        )

    def save(self) -> None:
        write_json(
            self.path,
            {
                "last_event_seq": self.last_event_seq,
                "last_status": self.last_status,
                "last_transition_snapshot": self.last_transition_snapshot,
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


def parse_event_lines(text: str) -> list[tuple[int, str]]:
    parsed: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("#"):
            continue
        head = line.split("|", 1)[0].strip()
        try:
            seq = int(head[1:].strip())
        except ValueError:
            continue
        parsed.append((seq, line))
    parsed.sort(key=lambda item: item[0])
    return parsed


def append_new_events(out_dir: Path, state: LoggerState, events_text: str) -> int:
    parsed = parse_event_lines(events_text)
    if not parsed:
        return 0

    batch_max = parsed[-1][0]
    if batch_max < state.last_event_seq:
        append_line(events_daily_path(out_dir), f"[{utc_now_iso()}] sequence reset detected")
        state.last_event_seq = 0

    written = 0
    for seq, line in parsed:
        if seq > state.last_event_seq:
            append_line(events_daily_path(out_dir), f"[{utc_now_iso()}] {line}")
            state.last_event_seq = seq
            written += 1
    return written


def transition_snapshot(status: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "mode",
        "alarm",
        "message",
        "routerConnected",
        "wifiState",
        "wifiRssi",
        "windRaw",
        "rainRaw",
        "waterRaw",
        "z1State",
        "z1ActiveCmd",
        "z1Event",
        "z1Temp",
        "z1Hum",
        "z1Level",
        "z1Close",
        "z1Errors",
        "z1TimerMs",
        "z1ElapsedMs",
        "z1RemainingMs",
        "z2State",
        "z2ActiveCmd",
        "z2Event",
        "z2Temp",
        "z2Hum",
        "z2Level",
        "z2Close",
        "z2Errors",
        "z2TimerMs",
        "z2ElapsedMs",
        "z2RemainingMs",
        "auxState",
        "auxEvent",
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


def log_fetch_error(out_dir: Path, kind: str, exc: Exception) -> None:
    message = f"{kind} fetch failed: {exc}"
    append_line(events_daily_path(out_dir), f"[{utc_now_iso()}] {message}")
    print_log(message)


def main() -> int:
    cfg = load_config()
    ensure_dir(cfg.out_dir)
    state = LoggerState(cfg.out_dir / "state.json")

    print_log(f"dualzone logger base_url={cfg.base_url} out_dir={cfg.out_dir}")

    next_status = 0.0
    next_events = 0.0

    while True:
        now = time.monotonic()
        if now >= next_status:
            try:
                status = fetch_json(f"{cfg.base_url}/status", cfg.timeout_sec)
                append_status_snapshot(cfg.out_dir, status, cfg.base_url)
                changes = append_transition_log(cfg.out_dir, state, status)
                state.last_status = status
                state.save()
                print_log(f"status logged changes={changes}")
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                log_fetch_error(cfg.out_dir, "status", exc)
            next_status = now + cfg.status_interval_sec

        if now >= next_events:
            try:
                events = fetch_text(f"{cfg.base_url}/events?limit={cfg.events_limit}", cfg.timeout_sec)
                written = append_new_events(cfg.out_dir, state, events)
                state.save()
                if written:
                    print_log(f"events appended={written}")
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                log_fetch_error(cfg.out_dir, "events", exc)
            next_events = now + cfg.events_interval_sec

        time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
