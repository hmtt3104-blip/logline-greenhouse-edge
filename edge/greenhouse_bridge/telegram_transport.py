from __future__ import annotations

import json
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .performance import duration_ms, get_performance_logger


class TelegramTransport:
    """Long-polling Telegram transport.

    Raspberry uses Bot API here. Android app reads the same service chat through TDLib.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        poll_timeout_sec: int = 20,
        api_base: str = "https://api.telegram.org",
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.poll_timeout_sec = poll_timeout_sec
        self.api_base = api_base.rstrip("/")
        self.perf_logger = get_performance_logger()
        self._next_offset: int | None = None

    def send_packet(self, packet: str) -> None:
        self._api_call(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": packet,
                "disable_web_page_preview": True,
            },
            timeout_sec=15,
        )

    def poll_packets(self, timeout_sec: int | None = None) -> list[str]:
        payload: dict[str, Any] = {
            "timeout": timeout_sec if timeout_sec is not None else self.poll_timeout_sec,
            "allowed_updates": ["message"],
        }
        if self._next_offset is not None:
            payload["offset"] = self._next_offset

        response = self._api_call(
            "getUpdates",
            payload,
            timeout_sec=(timeout_sec if timeout_sec is not None else self.poll_timeout_sec) + 10,
        )

        packets: list[str] = []
        for update in response:
            update_id = int(update["update_id"])
            self._next_offset = update_id + 1
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            if str(chat.get("id")) != self.chat_id:
                continue
            text = message.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            if not self._looks_like_packet(text):
                continue
            packets.append(text.strip())

        return packets

    def _api_call(self, method: str, payload: dict[str, Any], timeout_sec: int) -> Any:
        started_at = monotonic()
        payload_size_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        result_size = 0
        status = "OK"
        request = Request(
            f"{self.api_base}/bot{self.bot_token}/{method}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_sec) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:  # pragma: no cover - network dependent
            status = "HTTP_ERROR"
            body = exc.read().decode("utf-8", errors="replace")
            self.perf_logger.log_event(
                "telegram_api_call",
                method=method,
                timeout_sec=timeout_sec,
                duration_ms=duration_ms(started_at),
                payload_size_bytes=payload_size_bytes,
                response_size_bytes=len(body.encode("utf-8", errors="replace")),
                status=status,
                error=f"HTTP {exc.code}",
            )
            raise RuntimeError(f"Telegram API HTTPError {exc.code}: {body}") from exc
        except URLError as exc:  # pragma: no cover - network dependent
            status = "ERROR"
            self.perf_logger.log_event(
                "telegram_api_call",
                method=method,
                timeout_sec=timeout_sec,
                duration_ms=duration_ms(started_at),
                payload_size_bytes=payload_size_bytes,
                status=status,
                error=str(exc),
            )
            raise RuntimeError(f"Telegram API URLError: {exc}") from exc

        if not data.get("ok"):
            status = "API_ERROR"
            result_size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            self.perf_logger.log_event(
                "telegram_api_call",
                method=method,
                timeout_sec=timeout_sec,
                duration_ms=duration_ms(started_at),
                payload_size_bytes=payload_size_bytes,
                response_size_bytes=result_size,
                status=status,
                error="api_not_ok",
            )
            raise RuntimeError(f"Telegram API error for {method}: {data}")
        result = data.get("result")
        if result is not None:
            result_size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        self.perf_logger.log_event(
            "telegram_api_call",
            method=method,
            timeout_sec=timeout_sec,
            duration_ms=duration_ms(started_at),
            payload_size_bytes=payload_size_bytes,
            response_size_bytes=result_size,
            result_count=len(result) if isinstance(result, list) else None,
            status=status,
        )
        return result

    @staticmethod
    def _looks_like_packet(text: str) -> bool:
        stripped = text.strip()
        return (
            stripped.startswith("GHB1|")
            or (stripped.startswith("{") and '"ciphertext_b64"' in stripped and '"nonce_b64"' in stripped)
        )
