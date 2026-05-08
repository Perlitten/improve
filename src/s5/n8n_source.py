"""
N8nWebhookServer — минимальный HTTP-сервер для приёма задач от n8n.

Порт 8792 (только localhost). n8n шлёт POST /webhook/n8n с JSON-телом.
"""
from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s5.source_router import SourceRouter

log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8792


class N8nWebhookServer:
    """
    HTTP-сервер для n8n webhooks.

    Принимает POST /webhook/n8n:
        {"message": "текст задачи", "priority": 5, "metadata": {}, "idempotency_key": "..."}

    Отвечает:
        200 {"ok": true,  "inbox_id": "uuid"}
        200 {"ok": false, "reason": "duplicate"}
        400 {"ok": false, "error": "..."}
    """

    def __init__(
        self,
        router: "SourceRouter",
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        self._router = router
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> threading.Thread:
        handler = _make_handler(self._router)
        self._server = HTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="n8n-webhook",
        )
        self._thread.start()
        log.info("N8nWebhookServer listening on %s:%s", self._host, self._port)
        return self._thread

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=5)


def _make_handler(router: "SourceRouter"):
    class _N8nHandler(BaseHTTPRequestHandler):
        _router = router

        def do_POST(self) -> None:
            if self.path != "/webhook/n8n":
                self._respond(404, {"ok": False, "error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                payload = json.loads(body)
            except Exception as exc:
                self._respond(400, {"ok": False, "error": f"bad_request: {exc}"})
                return

            message = str(payload.get("message") or "").strip()
            if not message:
                self._respond(400, {"ok": False, "error": "message_required"})
                return

            priority = int(payload.get("priority") or 5)
            metadata = payload.get("metadata") or {}
            idem_key = payload.get("idempotency_key") or None
            metadata["n8n_source"] = True

            try:
                inbox_id = self._router.submit(
                    message=message,
                    source="n8n",
                    priority=max(1, min(10, priority)),
                    metadata=metadata,
                    idempotency_key=idem_key,
                )
            except Exception as exc:
                log.exception("N8nWebhook: submit error")
                self._respond(500, {"ok": False, "error": str(exc)[:200]})
                return

            if inbox_id:
                self._respond(200, {"ok": True, "inbox_id": inbox_id})
            else:
                self._respond(200, {"ok": False, "reason": "duplicate"})

        def _respond(self, code: int, data: dict) -> None:
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:  # suppress default logging
            log.debug("n8n-webhook: " + fmt, *args)

    return _N8nHandler
