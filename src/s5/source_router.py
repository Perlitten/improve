"""
SourceRouter — центральная точка приёма задач из всех источников.

Дедупликация: один и тот же (source, message) не попадёт в inbox дважды
за последний час. Ключ = sha256(source + ":" + message)[:16].
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from task_orchestrator_v2 import TaskOrchestrator


class SourceRouter:
    """
    Единая точка входа для всех источников задач.
    Дедуплицирует по idempotency_key в окне 1 час.
    """

    DEDUP_WINDOW = "1 hour"

    def __init__(self, orchestrator: "TaskOrchestrator") -> None:
        self._orch = orchestrator

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        message: str,
        source: str,
        priority: int = 5,
        metadata: dict | None = None,
        idempotency_key: str | None = None,
    ) -> str | None:
        """
        Принять сообщение и добавить в inbox (если не дубль).

        Returns:
            inbox_id (str) — если задача принята
            None            — если дубль
        """
        message = (message or "").strip()
        if not message:
            return None

        key = idempotency_key or self._compute_key(message, source)
        meta = dict(metadata or {})
        meta["idempotency_key"] = key

        if self._is_duplicate(source, key):
            return None

        return self._orch.enqueue(
            message=message,
            source=source,
            priority=priority,
            metadata=meta,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_key(self, message: str, source: str) -> str:
        raw = f"{source}:{message}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _is_duplicate(self, source: str, key: str) -> bool:
        """
        SELECT EXISTS проверка через тот же DB-коннект что у orchestrator.
        Импортируем get_db_connection внутри чтобы не тянуть psycopg2 на уровне модуля.
        """
        try:
            from task_orchestrator_v2 import get_db_connection

            with get_db_connection(self._orch.dbname) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM agent_inbox
                            WHERE source = %s
                              AND metadata->>'idempotency_key' = %s
                              AND created_at > NOW() - INTERVAL '1 hour'
                        )
                        """,
                        (source, key),
                    )
                    row = cur.fetchone()
                    return bool(row and row[0])
        except Exception:
            # При ошибке БД — пропускаем дедупликацию, не теряем сообщение
            return False
