from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import CommandRequest, TelemetrySnapshot

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - depends on target runtime
    AESGCM = None  # type: ignore[assignment]


class CryptoBox:
    """App-layer payload encryption over Telegram transport."""

    _COMPACT_PREFIX = "GHB1"
    _DIRECTION_TO_TOKEN = {
        "pi_to_app": "p2a",
        "app_to_pi": "a2p",
    }
    _TOKEN_TO_DIRECTION = {value: key for key, value in _DIRECTION_TO_TOKEN.items()}

    def __init__(self, pi_to_app_key_b64: str, app_to_pi_key_b64: str, default_ttl_sec: int = 60):
        if AESGCM is None:
            raise RuntimeError(
                "cryptography is required for AES-256-GCM envelopes. "
                "Install it from raspberry/requirements.txt on the target host."
            )

        self._pi_to_app = AESGCM(self._decode_key(pi_to_app_key_b64))
        self._app_to_pi = AESGCM(self._decode_key(app_to_pi_key_b64))
        self._default_ttl_sec = default_ttl_sec
        self._outgoing_seq = 0
        self._seen_incoming_seq: set[int] = set()

    def seal_telemetry(self, snapshot: TelemetrySnapshot) -> str:
        payload = self._compact_telemetry_payload(snapshot)
        return self._seal_payload(payload, direction="pi_to_app", ttl_sec=self._default_ttl_sec)

    def seal_command_status(self, payload: dict[str, Any]) -> str:
        return self._seal_payload(payload, direction="pi_to_app", ttl_sec=self._default_ttl_sec)

    def open_command(self, packet: str) -> CommandRequest:
        payload = self._open_payload(packet, expected_direction="app_to_pi")
        if payload.get("type") != "command":
            raise ValueError("Envelope payload is not a command")
        return CommandRequest(
            cmd_id=str(payload["cmd_id"]),
            seq=int(payload["seq"]),
            ts=str(payload["ts"]),
            ttl_sec=int(payload["ttl_sec"]),
            target=str(payload["target"]),
            action=str(payload["action"]),
            params=dict(payload.get("params", {})),
        )

    def _seal_payload(self, payload: dict[str, Any], direction: str, ttl_sec: int) -> str:
        sent_at = self._now_iso()
        seq = self._next_outgoing_seq()
        aad_obj = {
            "v": 1,
            "dir": direction,
            "alg": "AES-256-GCM",
            "sent_at": sent_at,
            "ttl_sec": ttl_sec,
            "seq": seq,
        }
        aad = json.dumps(aad_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
        plaintext = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        nonce = os.urandom(12)
        cipher = self._pi_to_app if direction == "pi_to_app" else self._app_to_pi
        ciphertext = cipher.encrypt(nonce, plaintext, aad)
        return self._pack_compact_envelope(
            direction=direction,
            sent_at=sent_at,
            ttl_sec=ttl_sec,
            seq=seq,
            nonce=nonce,
            ciphertext=ciphertext,
        )

    def _open_payload(self, packet: str, expected_direction: str) -> dict[str, Any]:
        envelope = self._parse_envelope(packet)
        direction = envelope["dir"]
        if direction != expected_direction:
            raise ValueError(f"Unexpected envelope direction: {direction}")
        aad_obj = {
            "v": envelope["v"],
            "dir": envelope["dir"],
            "alg": envelope["alg"],
            "sent_at": envelope["sent_at"],
            "ttl_sec": envelope["ttl_sec"],
            "seq": envelope.get("seq"),
        }
        self._prevalidate_envelope(aad_obj)
        aad = json.dumps(aad_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
        nonce = self._b64_decode(envelope["nonce_b64"])
        ciphertext = self._b64_decode(envelope["ciphertext_b64"])
        cipher = self._app_to_pi if expected_direction == "app_to_pi" else self._pi_to_app
        plaintext = cipher.decrypt(nonce, ciphertext, aad)
        self._validate_replay(aad_obj.get("seq"))
        return json.loads(plaintext.decode("utf-8"))

    def _parse_envelope(self, packet: str) -> dict[str, Any]:
        stripped = packet.strip()
        if stripped.startswith(f"{self._COMPACT_PREFIX}|"):
            parts = stripped.split("|", 6)
            if len(parts) != 7:
                raise ValueError("Invalid compact envelope field count")
            _, direction_token, sent_at_epoch, ttl_sec, seq, nonce_b64, ciphertext_b64 = parts
            direction = self._TOKEN_TO_DIRECTION.get(direction_token)
            if direction is None:
                raise ValueError(f"Unknown compact direction token: {direction_token}")
            sent_at = self._iso_from_epoch_seconds(int(sent_at_epoch))
            return {
                "v": 1,
                "dir": direction,
                "alg": "AES-256-GCM",
                "sent_at": sent_at,
                "ttl_sec": int(ttl_sec),
                "seq": int(seq),
                "nonce_b64": nonce_b64,
                "ciphertext_b64": ciphertext_b64,
            }

        return json.loads(stripped)

    def _pack_compact_envelope(
        self,
        direction: str,
        sent_at: str,
        ttl_sec: int,
        seq: int,
        nonce: bytes,
        ciphertext: bytes,
    ) -> str:
        direction_token = self._DIRECTION_TO_TOKEN[direction]
        return "|".join(
            [
                self._COMPACT_PREFIX,
                direction_token,
                str(self._epoch_seconds_from_iso(sent_at)),
                str(ttl_sec),
                str(seq),
                self._b64_encode(nonce),
                self._b64_encode(ciphertext),
            ]
        )

    def _compact_telemetry_payload(self, snapshot: TelemetrySnapshot) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "telemetry",
            "g1": {
                "z1": self._compact_zone(snapshot.g1.zone1),
                "z2": self._compact_zone(snapshot.g1.zone2),
            },
            "g2": {
                "d": self._compact_triple(snapshot.g2.temp, snapshot.g2.humidity, snapshot.g2.state),
            },
        }

        if snapshot.g1.mode is not None:
            payload["g1"]["m"] = self._short_text(snapshot.g1.mode, 12)
        if snapshot.g1.alarm is not None:
            payload["g1"]["a"] = self._short_text(snapshot.g1.alarm, 24)
        if snapshot.g1.router_status is not None:
            payload["g1"]["r"] = self._short_text(snapshot.g1.router_status, 18)
        if snapshot.g1.router_url is not None:
            payload["g1"]["u"] = self._short_text(snapshot.g1.router_url, 28)
        if snapshot.g2.mode is not None:
            payload["g2"]["m"] = self._short_text(snapshot.g2.mode, 12)
        if snapshot.g2.last_action is not None:
            payload["g2"]["a"] = self._short_text(snapshot.g2.last_action, 24)
        if snapshot.g2.router_status is not None:
            payload["g2"]["r"] = self._short_text(snapshot.g2.router_status, 18)
        if snapshot.g2.router_url is not None:
            payload["g2"]["u"] = self._short_text(snapshot.g2.router_url, 28)
        if self._has_temperature_node_data(snapshot.temperature_node):
            payload["t3"] = {
                "t": self._short_text(snapshot.temperature_node.title, 20),
                "s1": self._compact_temperature_probe(snapshot.temperature_node.sensor1),
                "s2": self._compact_temperature_probe(snapshot.temperature_node.sensor2),
                "s3": self._compact_temperature_probe(snapshot.temperature_node.outside),
                "r": self._short_text(snapshot.temperature_node.router_status, 18),
                "u": self._short_text(snapshot.temperature_node.router_url, 28),
                "n": self._short_text(snapshot.temperature_node.note, 32),
            }

        return payload

    @staticmethod
    def _compact_zone(zone: Any) -> list[Any]:
        return CryptoBox._compact_triple(zone.temp, zone.humidity, zone.state)

    @staticmethod
    def _compact_triple(temp: Any, humidity: Any, state: Any) -> list[Any]:
        return [temp, humidity, CryptoBox._short_text(state, 16)]

    @staticmethod
    def _compact_temperature_probe(probe: Any) -> list[Any]:
        return [
            CryptoBox._short_text(probe.label, 14),
            probe.temp,
            probe.humidity,
            CryptoBox._short_text(probe.status, 20),
            probe.errors,
            CryptoBox._short_text(probe.last_good_ago, 20),
        ]

    @staticmethod
    def _has_temperature_node_data(node: Any) -> bool:
        return any(
            value is not None and value != ""
            for value in (
                node.sensor1.temp,
                node.sensor1.humidity,
                node.sensor2.temp,
                node.sensor2.humidity,
                node.outside.temp,
                node.outside.humidity,
                node.router_status,
                node.note,
            )
        )

    @staticmethod
    def _short_text(value: Any, limit: int) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text[:limit]

    def _prevalidate_envelope(self, envelope: dict[str, Any]) -> None:
        if envelope.get("alg") != "AES-256-GCM":
            raise ValueError("Unsupported algorithm")
        sent_at = datetime.fromisoformat(str(envelope["sent_at"]).replace("Z", "+00:00"))
        ttl_sec = int(envelope["ttl_sec"])
        if sent_at + timedelta(seconds=ttl_sec) < datetime.now(timezone.utc):
            raise ValueError("Envelope expired")

    def _validate_replay(self, seq: Any) -> None:
        if seq is None:
            return
        seq = int(seq)
        if seq in self._seen_incoming_seq:
            raise ValueError(f"Replay detected for seq={seq}")
        self._seen_incoming_seq.add(seq)

    def _next_outgoing_seq(self) -> int:
        self._outgoing_seq += 1
        return self._outgoing_seq

    @staticmethod
    def _decode_key(key_b64: str) -> bytes:
        key = CryptoBox._b64_decode(key_b64)
        if len(key) != 32:
            raise ValueError("AES-256-GCM key must be exactly 32 bytes after base64 decoding")
        return key

    @staticmethod
    def _b64_encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64_decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _epoch_seconds_from_iso(value: str) -> int:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())

    @staticmethod
    def _iso_from_epoch_seconds(value: int) -> str:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
