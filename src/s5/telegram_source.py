"""
TelegramSource — long-polling адаптер Telegram Bot API.

Работает в daemon-thread. Принимает только сообщения из TELEGRAM_HOME_CHANNEL.
Вызывает SourceRouter.submit() для каждого нового сообщения.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib import request, error as urllib_error

if TYPE_CHECKING:
    from s5.source_router import SourceRouter

log = logging.getLogger(__name__)

# Файл для хранения последнего offset между перезапусками
_OFFSET_FILE = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes")) / "ralph_tg_offset.txt"


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


def _load_credentials() -> tuple[str, str]:
    """Возвращает (token, chat_id) из env-файлов или переменных окружения."""
    env: dict[str, str] = {}
    for p in ("/srv/automation/.env", str(Path.home() / ".hermes/.env")):
        env.update(_read_env(Path(p)))
    env.update(os.environ)
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_HOME_CHANNEL", "")
    return token, chat_id


class TelegramSource:
    """
    Long-polling Telegram бот.

    Запускается как daemon-thread через start().
    Принимает только текстовые сообщения из home channel.
    """

    POLL_TIMEOUT = 30   # секунды — long polling timeout
    RETRY_DELAY = 10    # секунды — пауза при ошибке API

    def __init__(self, router: "SourceRouter", token: str = "", chat_id: str = "") -> None:
        if not token or not chat_id:
            token, chat_id = _load_credentials()
        self._token = token
        self._chat_id = str(chat_id)
        self._router = router
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._offset = self._load_offset()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> threading.Thread:
        """Запускает polling в daemon-thread. Не блокирует."""
        if not self._token or not self._chat_id:
            log.warning("TelegramSource: no token/chat_id — skipping")
            return threading.Thread()  # no-op
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="tg-source")
        self._thread.start()
        log.info("TelegramSource started (chat_id=%s)", self._chat_id)
        return self._thread

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.POLL_TIMEOUT + 5)

    def send(self, text: str) -> bool:
        """Отправить сообщение в home channel. Возвращает True при успехе."""
        return self._api_call("sendMessage", {"chat_id": self._chat_id, "text": text[:4096]})

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                updates = self._get_updates()
                for upd in updates:
                    self._handle_update(upd)
            except Exception as exc:
                log.warning("TelegramSource poll error: %s", exc)
                self._stop.wait(self.RETRY_DELAY)

    def _get_updates(self) -> list[dict]:
        params = {
            "offset": self._offset,
            "timeout": self.POLL_TIMEOUT,
            "allowed_updates": ["message"],
        }
        url = f"https://api.telegram.org/bot{self._token}/getUpdates"
        body = json.dumps(params).encode()
        req = request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=self.POLL_TIMEOUT + 5) as resp:
                data = json.loads(resp.read())
        except urllib_error.URLError as exc:
            log.debug("Telegram getUpdates error: %s", exc)
            return []
        if not data.get("ok"):
            return []
        return data.get("result", [])

    def _handle_update(self, upd: dict) -> None:
        update_id: int = upd.get("update_id", 0)
        self._offset = update_id + 1
        self._save_offset(self._offset)

        msg = upd.get("message", {})
        text = (msg.get("text") or "").strip()
        if not text:
            return

        # Принимаем только из home channel
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != self._chat_id:
            log.debug("TelegramSource: ignored message from chat %s", chat_id)
            return

        from_user = msg.get("from", {})
        metadata = {
            "chat_id": chat_id,
            "message_id": msg.get("message_id"),
            "from_user_id": from_user.get("id"),
            "from_username": from_user.get("username"),
        }
        inbox_id = self._router.submit(
            message=text,
            source="telegram",
            priority=5,
            metadata=metadata,
        )
        if inbox_id:
            log.info("TelegramSource: enqueued inbox_id=%s", inbox_id)
        else:
            log.debug("TelegramSource: duplicate message skipped")

    def _api_call(self, method: str, payload: dict) -> bool:
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        body = json.dumps(payload).encode()
        req = request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            request.urlopen(req, timeout=15)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Offset persistence
    # ------------------------------------------------------------------

    def _load_offset(self) -> int:
        try:
            return int(_OFFSET_FILE.read_text().strip())
        except Exception:
            return 0

    def _save_offset(self, offset: int) -> None:
        try:
            _OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
            _OFFSET_FILE.write_text(str(offset))
        except Exception:
            pass
