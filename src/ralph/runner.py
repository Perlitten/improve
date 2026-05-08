"""
Ralph — автономный task runner (Phase 10 S8).

Polling loop: берёт задачи из agent_inbox через TaskOrchestrator.dequeue(),
отправляет в Hermes Gateway, сохраняет checkpoint, уведомляет в Telegram.

Ограничения автономии:
  - Обрабатывает только задачи с priority = 'low' или 'normal'
  - critical/high → pause(task_id, "requires_human") + Telegram-уведомление
  - Использует только бесплатные NVIDIA NIM модели
  - ResourceGuard проверяется перед каждой итерацией

Запуск: python3 -m ralph.runner  (или через systemd ralph.service)
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# Приоритеты, которые Ralph обрабатывает без человека
ALLOWED_PRIORITIES = {"low", "normal"}

# Дефолтные параметры
DEFAULT_POLL_INTERVAL = 20      # секунды между итерациями при пустой очереди
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8000"
DEFAULT_GATEWAY_TIMEOUT = 300   # 5 минут на выполнение задачи


class RalphRunner:
    """
    Главный цикл Ralph.

    Поднимает S5 источники в daemon-threads, сам работает в главном потоке.
    """

    def __init__(
        self,
        orchestrator,
        gateway,
        notifier,
        router,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._orch = orchestrator
        self._gw = gateway
        self._notifier = notifier
        self._router = router
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._sources: list = []  # S5 source instances

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_sources(self) -> None:
        """Запускает S5 источники (Telegram, n8n, API) в daemon-threads."""
        try:
            from s5.telegram_source import TelegramSource
            tg = TelegramSource(router=self._router)
            tg.start()
            self._sources.append(tg)
            log.info("S5: TelegramSource started")
        except Exception as exc:
            log.warning("S5: TelegramSource failed to start: %s", exc)

        try:
            from s5.n8n_source import N8nWebhookServer
            n8n = N8nWebhookServer(router=self._router)
            n8n.start()
            self._sources.append(n8n)
            log.info("S5: N8nWebhookServer started on :8792")
        except Exception as exc:
            log.warning("S5: N8nWebhookServer failed to start: %s", exc)

        try:
            from s5.api_source import ApiInboxServer
            api = ApiInboxServer(router=self._router, orchestrator=self._orch)
            api.start()
            self._sources.append(api)
            log.info("S5: ApiInboxServer started on :8793")
        except Exception as exc:
            log.warning("S5: ApiInboxServer failed to start: %s", exc)

    def run(self) -> None:
        """
        Главный блокирующий цикл.

        Выход: self._stop.set() (SIGTERM handler или stop()).
        """
        log.info("Ralph runner started (poll_interval=%ds)", self._poll_interval)
        if self._notifier:
            self._notifier.send("🟢 *Ralph запущен.* Жду задачи из inbox.")

        while not self._stop.is_set():
            try:
                self._iteration()
            except Exception as exc:
                log.exception("Ralph: unexpected error in iteration: %s", exc)
                # Короткая пауза чтобы не спамить при системной ошибке
                self._stop.wait(5)

        log.info("Ralph runner stopped")
        if self._notifier:
            self._notifier.send("🔴 *Ralph остановлен.*")

    def stop(self) -> None:
        self._stop.set()
        for src in self._sources:
            try:
                src.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Core iteration
    # ------------------------------------------------------------------

    def _iteration(self) -> None:
        # 1. Resource preflight
        if not self._resource_check():
            self._stop.wait(self._poll_interval)
            return

        # 2. Dequeue следующую задачу
        task = None
        try:
            task = self._orch.dequeue()
        except Exception as exc:
            log.warning("Ralph: dequeue error: %s", exc)
            self._stop.wait(self._poll_interval)
            return

        if task is None:
            # Очередь пуста
            log.debug("Ralph: queue empty, sleeping %ds", self._poll_interval)
            self._stop.wait(self._poll_interval)
            return

        task_id = str(task.get("id") or task.get("task_id") or "?")
        message = self._extract_message(task)
        # prefer priority_text (string like "normal") over priority (int 1-10)
        priority = str(task.get("priority_text") or task.get("priority") or "normal")

        log.info("Ralph: dequeued task_id=%s priority=%s", task_id, priority)

        # 3. Проверяем что приоритет допустим для автономной обработки
        if not self._is_allowed_priority(priority, task_id):
            return  # уже pause() и notify_skipped() внутри

        # 4. Начальный checkpoint
        self._save_checkpoint(task_id, "started", {"message_preview": message[:200]})

        # 5. Notify user that we're working
        model_hint = self._pick_model()
        if self._notifier:
            self._notifier.notify_started(task_id, message, model_hint)

        # 6. Выполняем через gateway
        result = self._gw.run(message=message, task_id=task_id)

        # 7. Обрабатываем результат
        self._handle_result(task_id, task, message, result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resource_check(self) -> bool:
        """
        Проверяет ресурсы через ResourceGuard.
        Возвращает True если можно продолжать, False если заблокировано.
        """
        try:
            from resource_guard.resource_guard import (
                collect_snapshot,
                assess_resources,
            )
            snapshot = collect_snapshot()
            decision = assess_resources(snapshot, operation="agent_loop")
            if not decision.allowed:
                reasons = "; ".join(decision.blocked_reasons)
                log.warning("Ralph: ResourceGuard blocked — %s", reasons)
                return False
            if decision.warnings:
                log.debug("Ralph: ResourceGuard warnings: %s", decision.warnings)
            return True
        except ImportError:
            # ResourceGuard не установлен — продолжаем без проверки
            return True
        except Exception as exc:
            log.warning("Ralph: ResourceGuard check failed: %s — proceeding anyway", exc)
            return True

    def _is_allowed_priority(self, priority: str, task_id: str) -> bool:
        """
        Проверяет что задача допустима для автономной обработки.
        critical/high → pause + notify, returns False.
        """
        if priority in ALLOWED_PRIORITIES:
            return True

        reason = f"priority={priority} requires_human"
        log.info("Ralph: pausing task_id=%s (%s)", task_id, reason)
        try:
            self._orch.pause(task_id, reason)
        except Exception as exc:
            log.warning("Ralph: pause failed for task_id=%s: %s", task_id, exc)

        if self._notifier:
            self._notifier.notify_skipped(task_id, reason)
        return False

    def _handle_result(
        self, task_id: str, task: dict, message: str, result: dict
    ) -> None:
        response = result.get("response", "")
        error = result.get("error")
        model_used = result.get("model_used", "?")

        if result.get("ok"):
            log.info(
                "Ralph: task_id=%s COMPLETED model=%s latency=%dms",
                task_id, model_used, result.get("latency_ms", 0),
            )
            self._save_checkpoint(task_id, "completed", {
                "model_used": model_used,
                "response_preview": response[:500],
            })
            try:
                self._orch.complete(task_id)
            except Exception as exc:
                log.warning("Ralph: complete() failed: %s", exc)
            if self._notifier:
                self._notifier.notify_complete(task_id, message, response)
        else:
            # Определяем нужен ли retry
            meta = task.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            retry_count = int(meta.get("retry_count", 0))
            max_retries = int(meta.get("max_retries", 3))
            should_retry = retry_count < max_retries

            log.warning(
                "Ralph: task_id=%s FAILED error=%r retry=%s (%d/%d)",
                task_id, error, should_retry, retry_count, max_retries,
            )
            self._save_checkpoint(task_id, "failed", {"error": str(error)[:500]})
            try:
                self._orch.fail(task_id, str(error or "unknown"), should_retry=should_retry)
            except Exception as exc:
                log.warning("Ralph: fail() error: %s", exc)
            if self._notifier:
                self._notifier.notify_failed(task_id, message, str(error or ""), should_retry)

    def _extract_message(self, task: dict) -> str:
        """Извлечь текст задачи из task dict."""
        # Оркестратор возвращает разные поля в зависимости от версии
        for key in ("raw_text", "message", "goal", "title"):
            val = task.get(key)
            if val:
                return str(val).strip()
        return json.dumps(task, ensure_ascii=False)[:500]

    def _pick_model(self) -> str:
        from ralph.gateway_client import FREE_MODELS
        return FREE_MODELS[0] if FREE_MODELS else "default"

    def _save_checkpoint(self, task_id: str, status: str, data: dict) -> None:
        try:
            state = {
                "task_id": task_id,
                "status": status,
                "ts": datetime.now(timezone.utc).isoformat(),
                **data,
            }
            self._orch.checkpoint(task_id, state)
        except Exception as exc:
            log.debug("Ralph: checkpoint save failed: %s", exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    level = os.getenv("RALPH_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [ralph] %(levelname)s %(message)s",
        stream=sys.stdout,
    )


def main() -> None:
    _setup_logging()

    # Добавляем пути чтобы импорты работали из любого cwd
    for p in ("/srv/automation/bin", "/usr/local/bin", "/home/Bilirubin/workspace/hermes/src"):
        if p not in sys.path:
            sys.path.insert(0, p)

    from task_orchestrator_v2 import TaskOrchestrator
    from s5.source_router import SourceRouter
    from ralph.gateway_client import GatewayClient
    from ralph.notifier import TelegramNotifier

    orchestrator = TaskOrchestrator()
    router = SourceRouter(orchestrator)
    gateway = GatewayClient(
        gateway_url=os.getenv("RALPH_GATEWAY_URL", DEFAULT_GATEWAY_URL),
        timeout=int(os.getenv("RALPH_GATEWAY_TIMEOUT", DEFAULT_GATEWAY_TIMEOUT)),
    )
    notifier = TelegramNotifier.from_env()
    poll_interval = int(os.getenv("RALPH_POLL_INTERVAL", DEFAULT_POLL_INTERVAL))

    runner = RalphRunner(
        orchestrator=orchestrator,
        gateway=gateway,
        notifier=notifier,
        router=router,
        poll_interval=poll_interval,
    )

    # Graceful shutdown при SIGTERM/SIGINT
    def _shutdown(signum, frame):
        log.info("Ralph: received signal %s, stopping...", signum)
        runner.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Запускаем S5 источники в daemon-threads
    runner.start_sources()

    # Главный цикл (блокирует до stop())
    runner.run()


if __name__ == "__main__":
    main()
