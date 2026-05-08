"""
ApiInboxServer — HTTP-сервер для прямого API доступа к inbox.

Порт 8793 (только localhost или за nginx). Bearer-auth через RALPH_API_TOKEN.

Endpoints:
  POST /inbox          — принять задачу
  GET  /inbox/status   — статус задачи по task_id
  GET  /health         — liveness probe
"""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from s5.source_router import SourceRouter
    from task_orchestrator_v2 import TaskOrchestrator

log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8793


def _load_api_token() -> str:
    for p in ("/srv/automation/.env", str(Path.home() / ".hermes/.env")):
        try:
            for line in Path(p).read_text().splitlines():
                line = line.strip()
                if line.startswith("RALPH_API_TOKEN="):
                    return line.split("=", 1)[1].strip().strip("\"'")
        except Exception:
            pass
    return os.getenv("RALPH_API_TOKEN", "")


class ApiInboxServer:
    """
    Прямой HTTP API для inbox.

    POST /inbox
        Headers: Authorization: Bearer <RALPH_API_TOKEN>
        Body:     {"message": str, "priority": 1-10, "metadata": {}, "idempotency_key": str}
        Returns:  201 {"ok": true, "inbox_id": "uuid"}

    GET /inbox/status?task_id=<uuid>
        Returns: 200 {"ok": true, "task": {...}}

    GET /health
        Returns: 200 {"ok": true}
    """

    def __init__(
        self,
        router: "SourceRouter",
        orchestrator: "TaskOrchestrator",
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        self._router = router
        self._orch = orchestrator
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> threading.Thread:
        token = _load_api_token()
        handler = _make_handler(self._router, self._orch, token)
        self._server = HTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="api-inbox",
        )
        self._thread.start()
        log.info("ApiInboxServer listening on %s:%s", self._host, self._port)
        return self._thread

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=5)


def _make_handler(router: "SourceRouter", orch: "TaskOrchestrator", token: str):
    class _ApiHandler(BaseHTTPRequestHandler):
        _router = router
        _orch = orch
        _token = token

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._respond(200, {"ok": True})
                return
            if parsed.path == "/inbox/status":
                params = parse_qs(parsed.query)
                task_id = (params.get("task_id") or [""])[0]
                if not task_id:
                    self._respond(400, {"ok": False, "error": "task_id_required"})
                    return
                try:
                    task = self._orch.get_task_status(task_id)
                    self._respond(200, {"ok": True, "task": task})
                except Exception as exc:
                    self._respond(500, {"ok": False, "error": str(exc)[:200]})
                return
            self._respond(404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/inbox":
                self._respond(404, {"ok": False, "error": "not_found"})
                return

            if not self._check_auth():
                self._respond(401, {"ok": False, "error": "unauthorized"})
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

            try:
                inbox_id = self._router.submit(
                    message=message,
                    source="api",
                    priority=max(1, min(10, priority)),
                    metadata=metadata,
                    idempotency_key=idem_key,
                )
            except Exception as exc:
                log.exception("ApiInbox: submit error")
                self._respond(500, {"ok": False, "error": str(exc)[:200]})
                return

            if inbox_id:
                self._respond(201, {"ok": True, "inbox_id": inbox_id})
            else:
                self._respond(200, {"ok": False, "reason": "duplicate"})

        def _check_auth(self) -> bool:
            if not self._token:
                return True  # токен не настроен — localhost only, доверяем
            auth = self.headers.get("Authorization", "")
            return auth == f"Bearer {self._token}"

        def _respond(self, code: int, data: dict) -> None:
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:
            log.debug("api-inbox: " + fmt, *args)

    return _ApiHandler
