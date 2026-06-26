from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen


def api_call(bot_token: str, method: str, payload: dict) -> dict:
    request = Request(
        f"https://api.telegram.org/bot{bot_token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error for {method}: {data}")
    return data


def main() -> int:
    bot_token = os.environ.get("GREENHOUSE_BRIDGE_TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("Missing GREENHOUSE_BRIDGE_TELEGRAM_BOT_TOKEN")

    me = api_call(bot_token, "getMe", {})
    print("BOT:")
    print(json.dumps(me.get("result"), ensure_ascii=False, indent=2))

    updates = api_call(bot_token, "getUpdates", {"timeout": 1, "allowed_updates": ["message"]})
    print("\nUPDATES:")
    for update in updates.get("result", []):
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        print(
            json.dumps(
                {
                    "update_id": update.get("update_id"),
                    "chat_id": chat.get("id"),
                    "chat_type": chat.get("type"),
                    "chat_title": chat.get("title"),
                    "username": user.get("username"),
                    "first_name": user.get("first_name"),
                    "text": message.get("text"),
                },
                ensure_ascii=False,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
