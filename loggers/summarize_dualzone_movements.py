#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


OPEN_COMMANDS = {"STEP_OPEN", "FULL_OPEN"}
CLOSE_COMMANDS = {"STEP_CLOSE", "FULL_CLOSE", "EXTRA_CLOSE", "STARTUP_CLOSE"}


@dataclass
class MovementStart:
    timestamp: str
    zone: int
    direction: str
    command: str
    mode: str
    temp_c: float | None
    hum_pct: float | None
    level: str
    close_threshold: str
    errors: str
    event: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show when each zone started opening/closing based on dual-zone status logs."
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
        help="Only include selected day(s), e.g. --date 2026-05-21. Can be passed multiple times.",
    )
    parser.add_argument(
        "--zone",
        type=int,
        choices=[1, 2],
        help="Only show one zone.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Show only the last N detected movement starts.",
    )
    parser.add_argument(
        "--skip-startup",
        action="store_true",
        help="Skip STARTUP_CLOSE entries.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print summary as JSON instead of plain text.",
    )
    return parser.parse_args()


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in ("", "--", "null", "None"):
        return None
    cleaned = (
        text.replace("°C", "")
        .replace("%", "")
        .replace("В°C", "")
        .replace(",", ".")
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def classify_direction(command: str, state: str) -> str | None:
    if command in OPEN_COMMANDS:
        return "OPEN"
    if command in CLOSE_COMMANDS:
        return "CLOSE"

    upper_state = state.upper()
    if "ВІДКРИВА" in upper_state or "OPEN" in upper_state:
        return "OPEN"
    if "ЗАКРИВА" in upper_state or "ДОТЯЖ" in upper_state or "CLOSE" in upper_state:
        return "CLOSE"
    return None


def status_files(log_dir: Path, selected_dates: list[str]) -> list[Path]:
    if selected_dates:
        paths = [log_dir / f"status-{day}.ndjson" for day in selected_dates]
        return [path for path in paths if path.exists()]
    daily = sorted(log_dir.glob("status-*.ndjson"))
    if daily:
        return daily
    legacy = log_dir / "status.ndjson"
    return [legacy] if legacy.exists() else []


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


def movement_starts(records: list[dict[str, Any]], zone_filter: int | None, skip_startup: bool) -> list[MovementStart]:
    starts: list[MovementStart] = []
    previous_by_zone: dict[int, dict[str, str | None]] = {
        1: {"command": None, "direction": None, "state": None},
        2: {"command": None, "direction": None, "state": None},
    }

    zones = [zone_filter] if zone_filter else [1, 2]

    for record in records:
        for zone in zones:
            prefix = f"z{zone}"
            command = str(record.get(f"{prefix}ActiveCmd", "NONE") or "NONE")
            state = str(record.get(f"{prefix}State", "") or "")
            direction = classify_direction(command, state)

            previous = previous_by_zone[zone]
            prev_command = previous["command"]
            prev_direction = previous["direction"]

            is_start = (
                direction is not None
                and (
                    prev_direction is None
                    or command != prev_command
                )
            )

            if is_start:
                if skip_startup and command == "STARTUP_CLOSE":
                    previous_by_zone[zone] = {
                        "command": command,
                        "direction": direction,
                        "state": state,
                    }
                    continue

                starts.append(
                    MovementStart(
                        timestamp=str(record["loggedAt"]),
                        zone=zone,
                        direction=direction,
                        command=command,
                        mode=str(record.get("mode", "")),
                        temp_c=parse_float(record.get(f"{prefix}TempRaw", record.get(f"{prefix}Temp"))),
                        hum_pct=parse_float(record.get(f"{prefix}Hum")),
                        level=str(record.get(f"{prefix}Level", "")),
                        close_threshold=str(record.get(f"{prefix}Close", "")),
                        errors=str(record.get(f"{prefix}Errors", "")),
                        event=str(record.get(f"{prefix}Event", "")),
                        message=str(record.get("message", "")),
                    )
                )

            previous_by_zone[zone] = {
                "command": command if direction is not None else None,
                "direction": direction,
                "state": state if direction is not None else None,
            }

    return starts


def render_plain(starts: list[MovementStart]) -> str:
    if not starts:
        return "No movement starts found."

    lines: list[str] = []
    for item in starts:
        temp = "--" if item.temp_c is None else f"{item.temp_c:.1f}C"
        hum = "--" if item.hum_pct is None else f"{item.hum_pct:.1f}%"
        lines.append(
            f"{item.timestamp} | Zone {item.zone} | {item.direction:<5} | {item.command:<13} | "
            f"temp={temp} hum={hum} level={item.level} close={item.close_threshold} "
            f"mode={item.mode} errors={item.errors} | event={item.event} | msg={item.message}"
        )
    return "\n".join(lines)


def render_json(starts: list[MovementStart]) -> str:
    payload = [
        {
            "timestamp": item.timestamp,
            "zone": item.zone,
            "direction": item.direction,
            "command": item.command,
            "mode": item.mode,
            "temp_c": item.temp_c,
            "hum_pct": item.hum_pct,
            "level": item.level,
            "close_threshold": item.close_threshold,
            "errors": item.errors,
            "event": item.event,
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
    starts = movement_starts(records, args.zone, args.skip_startup)
    if args.limit and args.limit > 0:
        starts = starts[-args.limit :]

    output = render_json(starts) if args.json else render_plain(starts)
    print(output, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
