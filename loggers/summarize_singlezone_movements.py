#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class MovementStart:
    timestamp: str
    direction: str
    trigger: str
    mode: str
    state: str
    temp_c: float | None
    hum_pct: float | None
    level_c: float | None
    close_threshold_c: float | None
    sensor_errors: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show when the single-zone greenhouse started opening/closing from daily status logs."
    )
    parser.add_argument(
        "--dir",
        dest="log_dir",
        default=".",
        help="Directory with status-YYYY-MM-DD.ndjson files. Default: current directory.",
    )
    parser.add_argument(
        "--date",
        action="append",
        default=[],
        help="Only include selected day(s), e.g. --date 2026-05-23. Can be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Show only the last N detected movement starts.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print summary as JSON instead of plain text.",
    )
    return parser.parse_args()


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in ("", "--", "null", "None"):
        return None
    cleaned = text.replace("°C", "").replace("%", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_text(value: Any) -> str:
    return str(value or "").strip().upper()


def state_direction(state: str) -> str | None:
    upper = normalize_text(state)
    if "ВІДКРИВА" in upper or "OPEN" in upper:
        return "OPEN"
    if "ЗАКРИВА" in upper or "CLOSE" in upper:
        return "CLOSE"
    return None


def message_direction(message: str) -> str | None:
    upper = normalize_text(message)
    if "ВІДКРИ" in upper or "OPEN" in upper:
        return "OPEN"
    if "ЗАКРИ" in upper or "ДОТЯЖ" in upper or "CLOSE" in upper:
        return "CLOSE"
    return None


def status_files(log_dir: Path, selected_dates: list[str]) -> list[Path]:
    if selected_dates:
        paths = [log_dir / f"status-{day}.ndjson" for day in selected_dates]
        return [path for path in paths if path.exists()]
    return sorted(log_dir.glob("status-*.ndjson"))


def read_records(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and "loggedAt" in payload:
                records.append(payload)
    records.sort(key=lambda item: parse_timestamp(str(item["loggedAt"])))
    return records


def movement_starts(records: list[dict[str, Any]]) -> list[MovementStart]:
    starts: list[MovementStart] = []
    previous_direction: str | None = None
    previous_state = ""
    previous_level: float | None = None

    for record in records:
        state = str(record.get("state", "") or "")
        message = str(record.get("message", "") or "")
        level = parse_float(record.get("level"))
        direction = state_direction(state)
        trigger = "STATE"

        if direction is None:
            direction = message_direction(message)
            if direction is not None:
                trigger = "MESSAGE"

        if direction is None and level is not None and previous_level is not None and level != previous_level:
            direction = "OPEN" if level > previous_level else "CLOSE"
            trigger = "LEVEL_DELTA"

        is_start = (
            direction is not None
            and (
                previous_direction is None
                or direction != previous_direction
                or (trigger == "STATE" and state != previous_state)
            )
        )

        if is_start:
            starts.append(
                MovementStart(
                    timestamp=str(record["loggedAt"]),
                    direction=direction,
                    trigger=trigger,
                    mode=str(record.get("mode", "")),
                    state=state,
                    temp_c=parse_float(record.get("tempRaw", record.get("temp"))),
                    hum_pct=parse_float(record.get("hum")),
                    level_c=level,
                    close_threshold_c=parse_float(record.get("close")),
                    sensor_errors=str(record.get("sensorErrors", "")),
                    message=message,
                )
            )

        previous_direction = direction
        previous_state = state
        previous_level = level
        if direction is None:
            previous_direction = None

    return starts


def render_plain(starts: list[MovementStart]) -> str:
    if not starts:
        return "No movement starts found."

    lines: list[str] = []
    for item in starts:
        temp = "--" if item.temp_c is None else f"{item.temp_c:.1f}C"
        hum = "--" if item.hum_pct is None else f"{item.hum_pct:.1f}%"
        level = "--" if item.level_c is None else f"{item.level_c:.1f}C"
        close_threshold = "--" if item.close_threshold_c is None else f"{item.close_threshold_c:.1f}C"
        lines.append(
            f"{item.timestamp} | {item.direction:<5} | {item.trigger:<11} | "
            f"temp={temp} hum={hum} level={level} close={close_threshold} "
            f"mode={item.mode} state={item.state} errors={item.sensor_errors} | msg={item.message}"
        )
    return "\n".join(lines)


def render_json(starts: list[MovementStart]) -> str:
    payload = [
        {
            "timestamp": item.timestamp,
            "direction": item.direction,
            "trigger": item.trigger,
            "mode": item.mode,
            "state": item.state,
            "temp_c": item.temp_c,
            "hum_pct": item.hum_pct,
            "level_c": item.level_c,
            "close_threshold_c": item.close_threshold_c,
            "sensor_errors": item.sensor_errors,
            "message": item.message,
        }
        for item in starts
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> int:
    args = parse_args()
    log_dir = Path(args.log_dir)
    paths = status_files(log_dir, args.date)
    if not paths:
        print("No matching status-YYYY-MM-DD.ndjson files found.", flush=True)
        return 1

    records = read_records(paths)
    starts = movement_starts(records)
    if args.limit and args.limit > 0:
        starts = starts[-args.limit :]

    output = render_json(starts) if args.json else render_plain(starts)
    print(output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
