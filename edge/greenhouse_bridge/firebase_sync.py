from __future__ import annotations

import copy
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import BridgeConfig
from .models import TelemetrySnapshot


LOGGER = logging.getLogger("greenhouse_bridge.firebase")


class FirebaseSync:
    """Realtime Database sync for greenhouse state and commands."""

    ACTIVE_STATUSES = {"pending", "processing", "sent_to_esp", "esp_ack"}
    TERMINAL_STATUSES = {"done", "error", "expired"}

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.enabled = False
        self._state_refs: dict[str, Any] = {}
        self._pending_refs: dict[str, Any] = {}
        self._history_refs: dict[str, Any] = {}

        if not config.firebase_enabled:
            return

        if not config.firebase_database_url or not config.firebase_service_account_json:
            LOGGER.warning(
                "Firebase sync disabled: database URL or service account path is missing."
            )
            return

        service_account_path = Path(config.firebase_service_account_json).expanduser()
        if not service_account_path.is_file():
            LOGGER.warning(
                "Firebase sync disabled: service account JSON not found at %s",
                service_account_path,
            )
            return

        try:
            import firebase_admin
            from firebase_admin import credentials, db
        except ImportError:
            LOGGER.warning(
                "Firebase sync disabled: firebase_admin is not installed. "
                "Install raspberry/requirements.txt on the target host."
            )
            return

        app_name = "greenhouse_bridge"
        try:
            app = firebase_admin.get_app(app_name)
        except ValueError:
            app = firebase_admin.initialize_app(
                credentials.Certificate(str(service_account_path)),
                {"databaseURL": config.firebase_database_url},
                name=app_name,
            )

        self._state_refs = {
            "g1": db.reference(config.firebase_g1_state_path, app=app),
            "g2": db.reference(config.firebase_g2_state_path, app=app),
            "t3": db.reference(config.firebase_t3_state_path, app=app),
        }
        self._pending_refs = {
            "g1": db.reference(config.firebase_g1_commands_pending_path, app=app),
            "g2": db.reference(config.firebase_g2_commands_pending_path, app=app),
        }
        self._history_refs = {
            "g1": db.reference(config.firebase_g1_commands_history_path, app=app),
            "g2": db.reference(config.firebase_g2_commands_history_path, app=app),
        }
        self.enabled = True
        LOGGER.info(
            "Firebase sync enabled: g1(state=%s pending=%s history=%s) g2(state=%s pending=%s history=%s) t3(state=%s)",
            config.firebase_g1_state_path,
            config.firebase_g1_commands_pending_path,
            config.firebase_g1_commands_history_path,
            config.firebase_g2_state_path,
            config.firebase_g2_commands_pending_path,
            config.firebase_g2_commands_history_path,
            config.firebase_t3_state_path,
        )

    def publish_g1_snapshot(self, snapshot: TelemetrySnapshot, reason: str) -> None:
        self._publish_snapshot(
            greenhouse_key="g1",
            payload=asdict(snapshot.g1),
            alerts=[alert for alert in snapshot.alerts if alert.startswith("g1")],
            router_status=snapshot.g1.router_status,
            snapshot=snapshot,
            reason=reason,
        )

    def publish_g2_snapshot(self, snapshot: TelemetrySnapshot, reason: str) -> None:
        self._publish_snapshot(
            greenhouse_key="g2",
            payload=asdict(snapshot.g2),
            alerts=[alert for alert in snapshot.alerts if alert.startswith("g2")],
            router_status=snapshot.g2.router_status,
            snapshot=snapshot,
            reason=reason,
        )

    def publish_t3_snapshot(self, snapshot: TelemetrySnapshot, reason: str) -> None:
        self._publish_snapshot(
            greenhouse_key="t3",
            payload=asdict(snapshot.temperature_node),
            alerts=[alert for alert in snapshot.alerts if alert.startswith("t3")],
            router_status=snapshot.temperature_node.router_status,
            snapshot=snapshot,
            reason=reason,
        )

    def _publish_snapshot(
        self,
        *,
        greenhouse_key: str,
        payload: dict[str, Any],
        alerts: list[str],
        router_status: str | None,
        snapshot: TelemetrySnapshot,
        reason: str,
    ) -> None:
        if not self.enabled:
            return
        state_ref = self._state_ref_for(greenhouse_key)
        if state_ref is None:
            return

        payload["updated_at"] = snapshot.ts
        payload["last_seen"] = snapshot.ts
        payload["source"] = self.config.firebase_processing_by
        payload["online"] = self._is_online_status(router_status)
        payload["greenhouse_id"] = greenhouse_key
        payload["bridge_seq"] = snapshot.seq
        payload["bridge_reason"] = reason
        payload["stale_after_sec"] = self.config.firebase_stale_state_sec
        payload["alerts"] = alerts

        state_ref.set(payload)

    def claim_next_command(
        self,
        greenhouse_key: str,
        processing_by: str,
        now_iso: str,
        default_expire_sec: int,
    ) -> dict[str, Any] | None:
        pending_ref = self._pending_ref_for(greenhouse_key)
        history_ref = self._history_ref_for(greenhouse_key)
        if not self.enabled or pending_ref is None or history_ref is None:
            return None

        raw_pending = pending_ref.get() or {}
        if not isinstance(raw_pending, dict):
            return None

        ordered = sorted(
            raw_pending.items(),
            key=lambda item: self._command_sort_key(item[0], item[1]),
        )
        for command_id, raw_command in ordered:
            if not isinstance(raw_command, dict):
                continue
            command = self._normalized_command(command_id, raw_command, greenhouse_key)
            if history_ref.child(command_id).get() is not None:
                LOGGER.warning(
                    "Dropping duplicate pending Firebase command %s from active %s queue",
                    command_id,
                    greenhouse_key,
                )
                pending_ref.child(command_id).delete()
                continue

            status = str(command.get("status") or "pending").strip()
            if status == "pending":
                if self._is_expired(command, now_iso, default_expire_sec):
                    self.complete_command(
                        greenhouse_key=greenhouse_key,
                        command_id=command_id,
                        status="expired",
                        now_iso=now_iso,
                        detail="Command expired before Raspberry execution.",
                    )
                    continue
                claimed = self._claim_command(
                    greenhouse_key=greenhouse_key,
                    command_id=command_id,
                    processing_by=processing_by,
                    now_iso=now_iso,
                )
                if claimed is not None:
                    LOGGER.info(
                        "Claimed Firebase %s command %s action=%s",
                        greenhouse_key,
                        command_id,
                        claimed.get("action"),
                    )
                    return claimed
            elif status in {"processing", "sent_to_esp", "esp_ack"}:
                if self._is_processing_stale(command, now_iso, default_expire_sec):
                    self.complete_command(
                        greenhouse_key=greenhouse_key,
                        command_id=command_id,
                        status="error",
                        now_iso=now_iso,
                        detail="Command was stuck in processing and was closed by Raspberry.",
                        error_message="stale_processing_marker",
                    )

        return None

    def update_active_command(
        self,
        greenhouse_key: str,
        command_id: str,
        status: str,
        now_iso: str,
        detail: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        pending_ref = self._pending_ref_for(greenhouse_key)
        if not self.enabled or pending_ref is None:
            return None

        ref = pending_ref.child(command_id)

        def transaction_update(current: Any) -> Any:
            if not isinstance(current, dict):
                return current
            updated = self._normalized_command(command_id, current, greenhouse_key)
            updated["status"] = status
            updated["updated_at"] = now_iso
            if detail is not None:
                updated["detail"] = detail
            if extra_fields:
                updated.update(extra_fields)
            updated["history"] = self._append_history(
                updated.get("history"),
                status=status,
                detail=detail,
                ts=now_iso,
            )
            return updated

        updated = ref.transaction(transaction_update)
        if not isinstance(updated, dict):
            return None
        return self._normalized_command(command_id, updated, greenhouse_key)

    def complete_command(
        self,
        greenhouse_key: str,
        command_id: str,
        status: str,
        now_iso: str,
        detail: str | None = None,
        device_state: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        pending_ref = self._pending_ref_for(greenhouse_key)
        history_ref = self._history_ref_for(greenhouse_key)
        if not self.enabled or pending_ref is None or history_ref is None:
            return None

        current = pending_ref.child(command_id).get()
        if not isinstance(current, dict):
            current = history_ref.child(command_id).get()
            if not isinstance(current, dict):
                return None

        final_doc = self._normalized_command(command_id, current, greenhouse_key)
        final_doc["status"] = status
        final_doc["updated_at"] = now_iso
        if detail is not None:
            final_doc["detail"] = detail
        if error_message is not None:
            final_doc["error_message"] = error_message
        if device_state is not None:
            final_doc["device_state"] = device_state
        if status == "done":
            final_doc["executed_at"] = now_iso
        elif status == "error":
            final_doc["failed_at"] = now_iso
        elif status == "expired":
            final_doc["expired_at"] = now_iso
        final_doc["history"] = self._append_history(
            final_doc.get("history"),
            status=status,
            detail=detail,
            ts=now_iso,
        )

        history_ref.child(command_id).set(final_doc)
        pending_ref.child(command_id).delete()
        LOGGER.info(
            "Moved Firebase %s command %s to history with status=%s",
            greenhouse_key,
            command_id,
            status,
        )
        return final_doc

    def _claim_command(
        self,
        greenhouse_key: str,
        command_id: str,
        processing_by: str,
        now_iso: str,
    ) -> dict[str, Any] | None:
        pending_ref = self._pending_ref_for(greenhouse_key)
        if pending_ref is None:
            return None

        ref = pending_ref.child(command_id)

        def transaction_update(current: Any) -> Any:
            if not isinstance(current, dict):
                return current
            updated = self._normalized_command(command_id, current, greenhouse_key)
            if str(updated.get("status") or "pending").strip() != "pending":
                return updated
            updated["status"] = "processing"
            updated["processing_by"] = processing_by
            updated["processing_at"] = now_iso
            updated["updated_at"] = now_iso
            updated["history"] = self._append_history(
                updated.get("history"),
                status="processing",
                detail=f"Claimed by {processing_by}",
                ts=now_iso,
            )
            return updated

        claimed = ref.transaction(transaction_update)
        if not isinstance(claimed, dict):
            return None
        command = self._normalized_command(command_id, claimed, greenhouse_key)
        if (
            command.get("status") == "processing"
            and command.get("processing_by") == processing_by
            and command.get("processing_at") == now_iso
        ):
            return command
        return None

    def _normalized_command(
        self,
        command_id: str,
        raw: dict[str, Any],
        greenhouse_key: str,
    ) -> dict[str, Any]:
        normalized = copy.deepcopy(raw)
        normalized["command_id"] = str(normalized.get("command_id") or command_id)
        normalized["target"] = str(normalized.get("target") or greenhouse_key)
        normalized["status"] = str(normalized.get("status") or "pending")
        return normalized

    def _append_history(
        self,
        current_history: Any,
        *,
        status: str,
        detail: str | None,
        ts: str,
    ) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        if isinstance(current_history, list):
            for item in current_history:
                if isinstance(item, dict):
                    history.append(copy.deepcopy(item))

        if history:
            last = history[-1]
            if last.get("status") == status and last.get("detail") == detail:
                last["ts"] = ts
                return history

        history.append({"status": status, "detail": detail, "ts": ts})
        return history

    def _is_expired(
        self,
        command: dict[str, Any],
        now_iso: str,
        default_expire_sec: int,
    ) -> bool:
        expires_at = self._parse_iso(command.get("expires_at"))
        if expires_at is None:
            created_at = self._parse_iso(command.get("created_at")) or self._parse_iso(now_iso)
            if created_at is None:
                return True
            expires_at = created_at + timedelta(seconds=default_expire_sec)
        now_dt = self._parse_iso(now_iso) or datetime.now(timezone.utc)
        return now_dt >= expires_at

    def _is_processing_stale(
        self,
        command: dict[str, Any],
        now_iso: str,
        default_expire_sec: int,
    ) -> bool:
        processing_at = self._parse_iso(command.get("processing_at")) or self._parse_iso(
            command.get("updated_at")
        )
        if processing_at is None:
            return self._is_expired(command, now_iso, default_expire_sec)
        now_dt = self._parse_iso(now_iso) or datetime.now(timezone.utc)
        max_age_sec = max(default_expire_sec, 30)
        return now_dt >= processing_at + timedelta(seconds=max_age_sec)

    def _command_sort_key(self, command_id: str, raw: Any) -> tuple[str, str]:
        if not isinstance(raw, dict):
            return ("9999-12-31T23:59:59+00:00", command_id)
        created_at = str(raw.get("created_at") or raw.get("updated_at") or "")
        return (created_at, command_id)

    @staticmethod
    def _is_online_status(status: str | None) -> bool:
        normalized = (status or "").strip().lower()
        return normalized in {
            "ok",
            "connected",
            "connected to router",
            "online",
            "wi-fi ok",
            "wifi ok",
            "підключено",
        }

    def _state_ref_for(self, greenhouse_key: str) -> Any | None:
        return self._state_refs.get(greenhouse_key)

    def _pending_ref_for(self, greenhouse_key: str) -> Any | None:
        return self._pending_refs.get(greenhouse_key)

    def _history_ref_for(self, greenhouse_key: str) -> Any | None:
        return self._history_refs.get(greenhouse_key)

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
