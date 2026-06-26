#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
LOG_PATH = SCRIPT_DIR / "logs" / "network_check.log"
NODE_RED_DATA_DIR = Path("/path/to/logline-greenhouse-edge/private/nodered-data-example")
DEFAULT_TIMEOUT_SEC = 2.0
PING_COUNT = 4
HTTP_ATTEMPTS = 3
IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
PACKET_LOSS_RE = re.compile(r"(\d+(?:\.\d+)?)%\s*packet loss")
RTT_RE = re.compile(
    r"(?:rtt|round-trip).*=\s*(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\s*ms"
)
MAC_RE = re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.IGNORECASE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log_jsonl(event: str, **fields: Any) -> None:
    payload = {"timestamp": utc_now_iso(), "event": event}
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def normalize_base_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    value = raw_url.strip().rstrip("/")
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.hostname:
        return None
    if parsed.port and parsed.port not in (80, 443):
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    return f"{parsed.scheme}://{parsed.hostname}"


def host_from_url(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(url).hostname


def is_ipv4(host: str | None) -> bool:
    return bool(host and IPV4_RE.match(host))


def default_gateway() -> str | None:
    try:
        proc = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except Exception:
        return None
    tokens = proc.stdout.split()
    if "via" in tokens:
        index = tokens.index("via")
        if index + 1 < len(tokens):
            return tokens[index + 1]
    return None


def resolve_host(host: str) -> dict[str, Any]:
    started_at = monotonic()
    try:
        infos = socket.getaddrinfo(host, None)
        resolved_ips = sorted({item[4][0] for item in infos if item[4]})
        return {
            "uses_dns": not is_ipv4(host),
            "resolve_ms": int(round((monotonic() - started_at) * 1000)),
            "resolved_ips": resolved_ips,
            "resolve_error": None,
        }
    except Exception as exc:
        return {
            "uses_dns": not is_ipv4(host),
            "resolve_ms": int(round((monotonic() - started_at) * 1000)),
            "resolved_ips": [],
            "resolve_error": str(exc),
        }


def ping_host(host: str, count: int = PING_COUNT, timeout_sec: int = int(DEFAULT_TIMEOUT_SEC)) -> dict[str, Any]:
    started_at = monotonic()
    cmd = ["ping", "-c", str(count), "-W", str(timeout_sec), host]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(5, count * timeout_sec + 2),
        )
    except Exception as exc:
        return {
            "status": "ERROR",
            "duration_ms": int(round((monotonic() - started_at) * 1000)),
            "packet_loss_pct": None,
            "avg_ms": None,
            "min_ms": None,
            "max_ms": None,
            "error": str(exc),
            "stdout": "",
        }

    stdout = proc.stdout.strip()
    packet_loss = None
    avg_ms = None
    min_ms = None
    max_ms = None
    loss_match = PACKET_LOSS_RE.search(stdout)
    if loss_match:
        packet_loss = float(loss_match.group(1))
    rtt_match = RTT_RE.search(stdout)
    if rtt_match:
        min_ms = float(rtt_match.group(1))
        avg_ms = float(rtt_match.group(2))
        max_ms = float(rtt_match.group(3))
    status = "OK" if proc.returncode == 0 else "ERROR"
    return {
        "status": status,
        "duration_ms": int(round((monotonic() - started_at) * 1000)),
        "packet_loss_pct": packet_loss,
        "avg_ms": avg_ms,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "error": None if proc.returncode == 0 else (proc.stderr.strip() or stdout or f"exit={proc.returncode}"),
        "stdout": stdout,
    }


def neighbor_info(host: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["ip", "neigh", "show", "to", host],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except Exception as exc:
        return {"raw": None, "mac": None, "state": None, "error": str(exc)}

    raw = proc.stdout.strip()
    mac_match = MAC_RE.search(raw)
    state = raw.split()[-1] if raw else None
    return {
        "raw": raw or None,
        "mac": mac_match.group(0).lower() if mac_match else None,
        "state": state,
        "error": None,
    }


def extract_first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in ("", None):
            return payload[key]
    return None


def http_status_probe(base_url: str, attempts: int = HTTP_ATTEMPTS, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
    durations: list[int] = []
    payload_size_bytes: list[int] = []
    statuses: list[str] = []
    last_payload: dict[str, Any] | None = None
    last_error: str | None = None

    for _ in range(attempts):
        started_at = monotonic()
        request = Request(
            f"{base_url.rstrip('/')}/status",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=timeout_sec) as response:
                body = response.read().decode("utf-8", errors="replace")
            durations.append(int(round((monotonic() - started_at) * 1000)))
            payload_size_bytes.append(len(body.encode("utf-8")))
            last_payload = json.loads(body)
            if not isinstance(last_payload, dict):
                raise ValueError("Unexpected /status payload")
            statuses.append("OK")
        except json.JSONDecodeError as exc:
            durations.append(int(round((monotonic() - started_at) * 1000)))
            statuses.append("PARSE_ERROR")
            last_error = str(exc)
        except HTTPError as exc:
            durations.append(int(round((monotonic() - started_at) * 1000)))
            statuses.append("HTTP_ERROR")
            last_error = f"HTTP {exc.code}"
        except URLError as exc:
            durations.append(int(round((monotonic() - started_at) * 1000)))
            statuses.append("TIMEOUT" if "timed out" in str(exc.reason).lower() else "ERROR")
            last_error = str(exc.reason)
        except Exception as exc:
            durations.append(int(round((monotonic() - started_at) * 1000)))
            statuses.append("ERROR")
            last_error = str(exc)

    ok_count = sum(1 for status in statuses if status == "OK")
    avg_duration_ms = round(sum(durations) / len(durations), 1) if durations else None
    response_router_url = None
    response_wifi_rssi = None
    if last_payload:
        response_router_url = extract_first(last_payload, "routerUrl", "router_url")
        response_wifi_rssi = extract_first(last_payload, "wifiRssi", "wifi_rssi")

    return {
        "status": "OK" if ok_count == attempts else ("WARNING" if ok_count > 0 else "ERROR"),
        "attempts": attempts,
        "ok_count": ok_count,
        "statuses": statuses,
        "avg_response_ms": avg_duration_ms,
        "min_response_ms": min(durations) if durations else None,
        "max_response_ms": max(durations) if durations else None,
        "response_size_bytes": max(payload_size_bytes) if payload_size_bytes else None,
        "last_error": last_error,
        "router_url": response_router_url,
        "wifi_rssi": response_wifi_rssi,
    }


def node_definition(label: str, env_key: str, latest_filename: str | None) -> dict[str, Any]:
    env = load_env_file(SCRIPT_DIR / ".env")
    env_url = normalize_base_url(env.get(env_key) or os.getenv(env_key))
    latest_url = None
    if latest_filename:
        latest = read_json(NODE_RED_DATA_DIR / latest_filename) or {}
        latest_url = normalize_base_url(
            extract_first(latest, "router_url", "routerUrl")
        )
    base_url = latest_url or env_url
    return {
        "label": label,
        "base_url": base_url,
        "env_url": env_url,
        "latest_url": latest_url,
    }


def classify_status(ping_result: dict[str, Any], http_result: dict[str, Any], wifi_rssi: Any) -> str:
    if ping_result["status"] != "OK" and http_result["status"] == "ERROR":
        return "ERROR"
    if http_result["status"] != "OK":
        return "WARNING"
    if ping_result["packet_loss_pct"] not in (None, 0.0):
        return "WARNING"
    try:
        if wifi_rssi is not None and int(float(wifi_rssi)) <= -75:
            return "WARNING"
    except Exception:
        pass
    return "OK"


def run_node_check(node: dict[str, Any]) -> dict[str, Any]:
    base_url = normalize_base_url(node.get("base_url"))
    if not base_url:
        return {
            "label": node["label"],
            "base_url": None,
            "status": "SKIPPED",
            "reason": "missing_base_url",
            "env_url": node.get("env_url"),
            "latest_url": node.get("latest_url"),
        }

    host = host_from_url(base_url)
    dns = resolve_host(host) if host else {"uses_dns": False, "resolve_ms": None, "resolved_ips": [], "resolve_error": None}
    ping_result = ping_host(host) if host else {"status": "ERROR", "error": "missing_host", "packet_loss_pct": None, "avg_ms": None, "min_ms": None, "max_ms": None, "duration_ms": None, "stdout": ""}
    http_result = http_status_probe(base_url)
    neigh = neighbor_info(host) if host else {"raw": None, "mac": None, "state": None, "error": "missing_host"}
    latest_host = host_from_url(node.get("latest_url"))
    env_host = host_from_url(node.get("env_url"))
    response_host = host_from_url(http_result.get("router_url"))
    ip_changed = bool(env_host and latest_host and env_host != latest_host)
    ip_mismatch = bool(response_host and host and response_host != host)
    final_status = classify_status(ping_result, http_result, http_result.get("wifi_rssi"))

    return {
        "label": node["label"],
        "base_url": base_url,
        "host": host,
        "env_url": node.get("env_url"),
        "latest_url": node.get("latest_url"),
        "uses_dns": dns["uses_dns"],
        "resolve_ms": dns["resolve_ms"],
        "resolved_ips": dns["resolved_ips"],
        "resolve_error": dns["resolve_error"],
        "ping": ping_result,
        "http": http_result,
        "neighbor": neigh,
        "wifi_rssi": http_result.get("wifi_rssi"),
        "ip_changed_vs_env": ip_changed,
        "ip_mismatch_vs_status": ip_mismatch,
        "status": final_status,
    }


def main() -> int:
    gateway = default_gateway()
    gateway_ping = ping_host(gateway) if gateway else {
        "status": "ERROR",
        "error": "default gateway not found",
        "packet_loss_pct": None,
        "avg_ms": None,
        "min_ms": None,
        "max_ms": None,
        "duration_ms": None,
        "stdout": "",
    }
    log_jsonl(
        "gateway_ping",
        host=gateway,
        status=gateway_ping.get("status"),
        packet_loss_pct=gateway_ping.get("packet_loss_pct"),
        avg_ms=gateway_ping.get("avg_ms"),
        error=gateway_ping.get("error"),
    )

    nodes = [
        node_definition(
            label="greenhouse1",
            env_key="GREENHOUSE_BRIDGE_GREENHOUSE1_BASE_URL",
            latest_filename="greenhouse1-latest.json",
        ),
        node_definition(
            label="greenhouse2",
            env_key="GREENHOUSE_BRIDGE_GREENHOUSE2_BASE_URL",
            latest_filename="greenhouse2-latest.json",
        ),
        node_definition(
            label="temperature_node",
            env_key="GREENHOUSE_BRIDGE_TEMPERATURE_NODE_BASE_URL",
            latest_filename=None,
        ),
    ]

    results = [run_node_check(node) for node in nodes]
    host_to_labels: dict[str, list[str]] = {}
    for result in results:
        host = result.get("host")
        if not host:
            continue
        host_to_labels.setdefault(host, []).append(result["label"])
    duplicate_hosts = {host: labels for host, labels in host_to_labels.items() if len(labels) > 1}

    overall_status = "OK"
    if gateway_ping.get("status") != "OK" or any(item["status"] == "ERROR" for item in results):
        overall_status = "ERROR"
    elif duplicate_hosts or any(item["status"] == "WARNING" for item in results):
        overall_status = "WARNING"

    for item in results:
        log_jsonl(
            "node_check",
            label=item["label"],
            base_url=item.get("base_url"),
            host=item.get("host"),
            status=item.get("status"),
            env_url=item.get("env_url"),
            latest_url=item.get("latest_url"),
            ip_changed_vs_env=item.get("ip_changed_vs_env"),
            ip_mismatch_vs_status=item.get("ip_mismatch_vs_status"),
            uses_dns=item.get("uses_dns"),
            resolve_ms=item.get("resolve_ms"),
            ping=item.get("ping"),
            http=item.get("http"),
            neighbor=item.get("neighbor"),
            wifi_rssi=item.get("wifi_rssi"),
        )

    log_jsonl(
        "summary",
        overall_status=overall_status,
        duplicate_hosts=duplicate_hosts,
        gateway=gateway,
        gateway_status=gateway_ping.get("status"),
        nodes_checked=len(results),
    )

    print(f"overall_status={overall_status}")
    print(f"gateway={gateway or '--'} ping_status={gateway_ping.get('status')}")
    if duplicate_hosts:
        print(f"duplicate_hosts={json.dumps(duplicate_hosts, ensure_ascii=False)}")
    for item in results:
        ping_avg = item.get("ping", {}).get("avg_ms")
        http_avg = item.get("http", {}).get("avg_response_ms")
        rssi = item.get("wifi_rssi")
        print(
            f"{item['label']}: status={item['status']} "
            f"host={item.get('host') or '--'} ping_avg_ms={ping_avg} "
            f"http_avg_ms={http_avg} wifi_rssi={rssi if rssi is not None else '--'}"
        )

    return 0 if overall_status != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
