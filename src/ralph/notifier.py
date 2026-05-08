"""
TelegramNotifier — fire-and-forget уведомления о результатах задач.

Паттерн идентичен send_telegram() из health_optimization_loop.py:
urllib без asyncio, токен из .env файлов.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib import request, error as urllib_error

log = logging.getLogger(__name__)


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip("\"'")
    return values


class TelegramNotifier:
    """
    Отправляет сообщения в Telegram. Молчит при любой ошибке.
    """

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = str(chat_id)

    # ------------------------------------------------------------------
    # High-level notifications
    # ------------------------------------------------------------------

    def notify_complete(self, task_id: str, message_preview: str, response_preview: str) -> None:
        text = (
            f"✅ *Задача выполнена*\n"
            f"`{task_id[:8]}`\n"
            f"*Запрос:* {self._trunc(message_preview, 120)}\n"
            f"*Ответ:* {self._trunc(response_preview, 300)}"
        )
        self.send(text, parse_mode="Markdown")

    def notify_failed(self, task_id: str, message_preview: str, error: str, retry: bool) -> None:
        retry_label = "🔄 будет повтор" if retry else "❌ повторов нет"
        text = (
            f"⚠️ *Задача не выполнена* ({retry_label})\n"
            f"`{task_id[:8]}`\n"
            f"*Запрос:* {self._trunc(message_preview, 100)}\n"
            f"*Ошибка:* `{self._trunc(error, 200)}`"
        )
        self.send(text, parse_mode="Markdown")

    def notify_skipped(self, task_id: str, reason: str) -> None:
        text = (
            f"⏸ *Задача требует участия человека*\n"
            f"`{task_id[:8]}`\n"
            f"Причина: {reason}"
        )
        self.send(text, parse_mode="Markdown")

    def notify_started(self, task_id: str, message_preview: str, model: str) -> None:
        text = (
            f"🤖 *Ralph берёт задачу*\n"
            f"`{task_id[:8]}`\n"
            f"*Запрос:* {self._trunc(message_preview, 150)}\n"
            f"*Модель:* `{model}`"
        )
        self.send(text, parse_mode="Markdown")

    # ------------------------------------------------------------------
    # Low-level send
    # ------------------------------------------------------------------

    def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Отправить сообщение. Возвращает True при успехе, False при любой ошибке."""
        if not self._token or not self._chat_id:
            return False
        payload = {
            "chat_id": self._chat_id,
            "text": text[:4096],
            "parse_mode": parse_mode,
        }
        body = json.dumps(payload).encode()
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        req = request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            request.urlopen(req, timeout=15)
            return True
        except urllib_error.URLError as exc:
            log.debug("TelegramNotifier send failed: %s", exc)
            return False
        except Exception as exc:
            log.debug("TelegramNotifier unexpected error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "TelegramNotifier | None":
        """Создать из .env файлов. Возвращает None если токен не настроен."""
        env: dict[str, str] = {}
        for p in ("/srv/automation/.env", str(Path.home() / ".hermes/.env")):
            env.update(_read_env(Path(p)))
        env.update(os.environ)
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = env.get("TELEGRAM_HOME_CHANNEL", "")
        if not token or not chat_id:
            return None
        return cls(token=token, chat_id=chat_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _trunc(text: str, max_len: int) -> str:
        text = str(text or "").strip()
        if len(text) <= max_len:
            return text
        return text[:max_len] + "…"
