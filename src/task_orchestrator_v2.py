#!/usr/bin/env python3
"""
Task Orchestrator V2: Adapted for production UUID schema.
Phase 10: Reliable Runtime — S2/S3/S4/S6/S7/S8/S9 complete.

This version works with the existing production schema:
- UUID-based IDs instead of SERIAL
- agent_inbox.active_task_id → agent_tasks.id relationship
- Production column names (raw_text, title, etc.)

Phase 10 additions:
  S6 — reprioritize()        Dynamic priority reordering
  S7 — Exponential backoff   fail() sets retry_after; dequeue() respects it
  S8 — queue_metrics()       Detailed queue statistics
  S9 — _audit() / audit log  Immutable event trail via task_audit_log table
"""

import json
import logging
import psycopg2
import psycopg2.extras
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
from contextlib import contextmanager
import uuid

log = logging.getLogger(__name__)


def _parse_jsonb(data):
    """
    Parse JSONB field safely.
    PostgreSQL returns JSONB as dict, not string.
    """
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        return json.loads(data)
    return {}


@contextmanager
def get_db_connection(dbname: str = "rag"):
    """Get database connection with automatic cleanup."""
    try:
        # Try to use unified config
        from config_loader import get_config
        config = get_config()

        db_user = config.get('database.user')
        db_password = config.get('database.password')

        # If config doesn't have DB credentials, use fallback
        if not db_user:
            raise ValueError("No database user in config")

        conn = psycopg2.connect(
            host=config.get('database.host', 'localhost'),
            port=config.get('database.port', 5432),
            dbname=config.get('database.name', dbname),
            user=db_user,
            password=db_password,
        )
    except (ImportError, FileNotFoundError, ValueError, KeyError):
        # Fallback to old method if config not available
        env_path = Path.home() / ".hermes/automation.env"
        env = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip()

        # Always use 'automation' user for production
        conn = psycopg2.connect(
            host="localhost",  # Use localhost for server
            port=5432,
            dbname=dbname,
            user="automation",  # Always use automation user
            password=env.get("POSTGRES_PASSWORD", ""),
        )

    try:
        yield conn
    finally:
        conn.close()


class TaskOrchestrator:
    """
    Persistent task queue with checkpoint/resume support.
    Adapted for production UUID schema.

    Features:
    - Tasks survive restarts
    - Checkpoint/resume for long-running tasks
    - Priority-based dequeue (S6: dynamic reprioritization)
    - Retry logic with exponential backoff (S7)
    - Detailed queue statistics (S8)
    - Immutable audit trail (S9)
    """

    # Priority mapping: int (1-10) to text
    PRIORITY_MAP = {
        1: 'critical',
        2: 'critical',
        3: 'high',
        4: 'high',
        5: 'normal',
        6: 'normal',
        7: 'low',
        8: 'low',
        9: 'low',
        10: 'low'
    }

    # Reverse mapping
    PRIORITY_REVERSE = {
        'critical': 1,
        'high': 3,
        'normal': 5,
        'low': 7
    }

    # S7: Backoff constants
    BACKOFF_BASE_SECONDS = 30   # base delay: 30s
    BACKOFF_MAX_SECONDS = 3600  # cap at 1 hour

    def __init__(self, dbname: str = "rag"):
        self.dbname = dbname

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _audit(
        self,
        cur,
        task_id: str,
        event: str,
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        actor: str = "system",
        reason: Optional[str] = None,
        extra: Optional[Dict] = None,
    ) -> None:
        """
        S9: Write one row to task_audit_log.

        Called inside an open cursor/transaction — does NOT commit.
        Silently skips if table doesn't exist (backwards compat).
        """
        try:
            payload: Dict[str, Any] = {}
            if reason:
                payload["reason"] = reason
            if extra:
                payload.update(extra)

            cur.execute(
                """
                INSERT INTO task_audit_log (
                    task_id, event, old_status, new_status,
                    actor, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    str(task_id),
                    event,
                    old_status,
                    new_status,
                    actor,
                    json.dumps(payload),
                ),
            )
        except Exception as exc:
            # Never let audit failure break the main transaction
            log.debug("_audit write failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(
        self,
        message: str,
        source: str,
        priority: int = 5,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Enqueue a new message to inbox.

        Args:
            message: Message text
            source: Source of message (telegram, n8n, api, etc.)
            priority: Priority 1-10 (1=highest)
            metadata: Additional context

        Returns:
            inbox_id: UUID of created inbox entry
        """
        if not 1 <= priority <= 10:
            raise ValueError("Priority must be between 1 and 10")

        priority_text = self.PRIORITY_MAP.get(priority, 'normal')

        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_inbox (
                        source, raw_text, redacted_text,
                        priority, status, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (source, message, message, priority_text, 'new',
                     json.dumps(metadata or {}))
                )
                inbox_id = cur.fetchone()[0]

                # S9: audit
                self._audit(
                    cur,
                    task_id=str(inbox_id),
                    event="enqueued",
                    new_status="new",
                    actor=source,
                    extra={"priority": priority_text, "source": source},
                )

                conn.commit()
                return str(inbox_id)

    def create_task(
        self,
        inbox_id: str,
        task_type: str,
        task_data: Dict,
        max_retries: int = 3
    ) -> str:
        """
        Create a task from inbox entry.

        Args:
            inbox_id: UUID reference to inbox entry
            task_type: Type of task (code_fix, analysis, etc.)
            task_data: Task-specific data
            max_retries: Maximum retry attempts (stored in metadata)

        Returns:
            task_id: UUID of created task
        """
        # Extract title and goal from task_data
        title = task_data.get('title', f'{task_type} task')
        goal = task_data.get('goal', '')
        domain = task_data.get('domain', task_type)

        # Store task_data and max_retries in metadata
        metadata = {
            'task_type': task_type,
            'task_data': task_data,
            'max_retries': max_retries,
            'retry_count': 0
        }

        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Create task
                cur.execute(
                    """
                    INSERT INTO agent_tasks (
                        title, domain, goal, status, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (title, domain, goal, 'queued', json.dumps(metadata))
                )
                task_id = cur.fetchone()[0]

                # Link task to inbox
                cur.execute(
                    """
                    UPDATE agent_inbox
                    SET active_task_id = %s, status = 'processing'
                    WHERE id = %s
                    """,
                    (task_id, inbox_id)
                )

                # S9: audit
                self._audit(
                    cur,
                    task_id=str(task_id),
                    event="created",
                    new_status="queued",
                    extra={"task_type": task_type, "inbox_id": str(inbox_id)},
                )

                conn.commit()
                return str(task_id)

    def dequeue(self) -> Optional[Dict]:
        """
        Dequeue next task by priority.

        S7: Respects retry_after — tasks with a future retry_after are skipped.

        Returns:
            Task dict or None if queue empty
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get highest priority queued task, honouring retry_after (S7)
                cur.execute(
                    """
                    SELECT
                        t.*,
                        i.raw_text as message_text,
                        i.source,
                        i.priority as priority_text,
                        i.metadata as inbox_metadata
                    FROM agent_tasks t
                    LEFT JOIN agent_inbox i ON i.active_task_id = t.id
                    WHERE t.status = 'queued'
                      AND (t.retry_after IS NULL OR t.retry_after <= NOW())
                    ORDER BY
                        CASE i.priority
                            WHEN 'critical' THEN 1
                            WHEN 'high' THEN 2
                            WHEN 'normal' THEN 3
                            WHEN 'low' THEN 4
                            ELSE 5
                        END ASC,
                        t.created_at ASC
                    LIMIT 1
                    FOR UPDATE OF t SKIP LOCKED
                    """
                )
                task = cur.fetchone()

                if not task:
                    return None

                # Mark as running
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = 'running', updated_at = NOW()
                    WHERE id = %s
                    """,
                    (task['id'],)
                )

                # S9: audit
                self._audit(
                    cur,
                    task_id=str(task['id']),
                    event="dequeued",
                    old_status="queued",
                    new_status="running",
                    actor="ralph",
                )

                conn.commit()

                # Convert to dict and parse JSON fields
                task_dict = dict(task)
                task_dict['status'] = 'running'  # Update status to reflect the change
                task_dict['metadata'] = _parse_jsonb(task_dict.get('metadata'))
                task_dict['inbox_metadata'] = _parse_jsonb(task_dict.get('inbox_metadata'))

                # Convert UUID strings to UUID objects for compatibility
                if 'id' in task_dict and isinstance(task_dict['id'], str):
                    task_dict['id'] = uuid.UUID(task_dict['id'])

                # Extract task_data from metadata
                task_dict['task_data'] = task_dict['metadata'].get('task_data', {})
                task_dict['task_type'] = task_dict['metadata'].get('task_type', 'unknown')

                # Map priority text to int
                task_dict['priority'] = self.PRIORITY_REVERSE.get(
                    task_dict.get('priority_text', 'normal'), 5
                )

                return task_dict

    def checkpoint(self, task_id: str, state: Dict) -> None:
        """
        Save checkpoint for task.

        Args:
            task_id: Task UUID
            state: State to save
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Get current metadata
                cur.execute(
                    "SELECT metadata FROM agent_tasks WHERE id = %s",
                    (task_id,)
                )
                row = cur.fetchone()
                if not row:
                    return

                metadata = _parse_jsonb(row[0])
                metadata['checkpoint_data'] = state

                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET metadata = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (json.dumps(metadata), task_id)
                )

                # S9: audit (lightweight — no status change)
                self._audit(
                    cur,
                    task_id=str(task_id),
                    event="checkpoint",
                    extra={"step": state.get("step"), "status": state.get("status")},
                )

                conn.commit()

    def resume(self, task_id: str) -> Optional[Dict]:
        """
        Resume a paused task.

        Args:
            task_id: Task UUID

        Returns:
            Task dict with checkpoint data or None
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        t.*,
                        i.raw_text as message_text,
                        i.source,
                        i.priority as priority_text,
                        i.metadata as inbox_metadata
                    FROM agent_tasks t
                    LEFT JOIN agent_inbox i ON i.active_task_id = t.id
                    WHERE t.id = %s AND t.status = 'paused'
                    """,
                    (task_id,)
                )
                task = cur.fetchone()

                if not task:
                    return None

                # Mark as running
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = 'running', updated_at = NOW()
                    WHERE id = %s
                    """,
                    (task_id,)
                )

                # S9: audit
                self._audit(
                    cur,
                    task_id=str(task_id),
                    event="resumed",
                    old_status="paused",
                    new_status="running",
                )

                conn.commit()

                # Convert to dict and parse JSON fields
                task_dict = dict(task)
                task_dict['status'] = 'running'  # Update status to reflect the change
                task_dict['metadata'] = _parse_jsonb(task_dict.get('metadata'))
                task_dict['inbox_metadata'] = _parse_jsonb(task_dict.get('inbox_metadata'))

                # Convert UUID strings to UUID objects
                if 'id' in task_dict and isinstance(task_dict['id'], str):
                    task_dict['id'] = uuid.UUID(task_dict['id'])

                # Extract checkpoint and task data
                task_dict['checkpoint_data'] = task_dict['metadata'].get('checkpoint_data')
                task_dict['task_data'] = task_dict['metadata'].get('task_data', {})
                task_dict['task_type'] = task_dict['metadata'].get('task_type', 'unknown')

                # Map priority
                task_dict['priority'] = self.PRIORITY_REVERSE.get(
                    task_dict.get('priority_text', 'normal'), 5
                )

                return task_dict

    def complete(self, task_id: str, result: Optional[Dict] = None) -> None:
        """
        Mark task as completed.

        Args:
            task_id: Task UUID
            result: Optional result data
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Capture old status for audit
                cur.execute("SELECT status FROM agent_tasks WHERE id = %s", (task_id,))
                row = cur.fetchone()
                old_status = row[0] if row else None

                # Update task
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = 'completed', updated_at = NOW()
                    WHERE id = %s
                    """,
                    (task_id,)
                )

                # Update inbox status
                cur.execute(
                    """
                    UPDATE agent_inbox
                    SET status = 'completed'
                    WHERE active_task_id = %s
                    """,
                    (task_id,)
                )

                # S9: audit
                self._audit(
                    cur,
                    task_id=str(task_id),
                    event="completed",
                    old_status=old_status,
                    new_status="completed",
                    actor="ralph",
                    extra={"has_result": result is not None},
                )

                conn.commit()

    def fail(self, task_id: str, error_message: str, should_retry: bool = True) -> None:
        """
        Mark task as failed.

        S7: Implements exponential backoff — retry_after = NOW() + 30s * 2^retry_count,
            capped at BACKOFF_MAX_SECONDS. The retry_after column must exist in agent_tasks.

        Args:
            task_id: Task UUID
            error_message: Error description
            should_retry: Whether to retry task
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Get current status + metadata
                cur.execute(
                    "SELECT status, metadata FROM agent_tasks WHERE id = %s",
                    (task_id,)
                )
                row = cur.fetchone()
                if not row:
                    return

                old_status = row[0]
                metadata = _parse_jsonb(row[1])
                retry_count = int(metadata.get('retry_count', 0))
                max_retries = int(metadata.get('max_retries', 3))

                # Check if should retry
                if should_retry and retry_count < max_retries:
                    # S7: Exponential backoff
                    delay_seconds = min(
                        self.BACKOFF_BASE_SECONDS * (2 ** retry_count),
                        self.BACKOFF_MAX_SECONDS,
                    )
                    metadata['retry_count'] = retry_count + 1
                    metadata['last_error'] = error_message[:500]

                    cur.execute(
                        """
                        UPDATE agent_tasks
                        SET status = 'queued',
                            metadata = %s,
                            error_text = %s,
                            retry_after = NOW() + (%s || ' seconds')::interval,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (json.dumps(metadata), error_message[:500], delay_seconds, task_id)
                    )

                    # S9: audit
                    self._audit(
                        cur,
                        task_id=str(task_id),
                        event="retry_scheduled",
                        old_status=old_status,
                        new_status="queued",
                        reason=error_message[:200],
                        extra={
                            "retry_count": metadata['retry_count'],
                            "max_retries": max_retries,
                            "delay_seconds": delay_seconds,
                        },
                    )
                else:
                    # Mark as failed
                    metadata['last_error'] = error_message[:500]

                    cur.execute(
                        """
                        UPDATE agent_tasks
                        SET status = 'failed',
                            metadata = %s,
                            error_text = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (json.dumps(metadata), error_message[:500], task_id)
                    )

                    # Mark inbox as failed
                    cur.execute(
                        """
                        UPDATE agent_inbox
                        SET status = 'failed'
                        WHERE active_task_id = %s
                        """,
                        (task_id,)
                    )

                    # S9: audit
                    self._audit(
                        cur,
                        task_id=str(task_id),
                        event="failed",
                        old_status=old_status,
                        new_status="failed",
                        reason=error_message[:200],
                        extra={
                            "retry_count": retry_count,
                            "max_retries": max_retries,
                            "exhausted": retry_count >= max_retries,
                        },
                    )

                conn.commit()

    def pause(self, task_id: str, reason: str, actor: str = "system") -> None:
        """
        Pause a running task.

        Args:
            task_id: Task UUID
            reason: Reason for pausing
            actor: Who triggered the pause
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Get current status + metadata
                cur.execute(
                    "SELECT status, metadata FROM agent_tasks WHERE id = %s",
                    (task_id,)
                )
                row = cur.fetchone()
                if not row:
                    return

                old_status = row[0]
                metadata = _parse_jsonb(row[1])
                metadata['pause_reason'] = reason

                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = 'paused',
                        metadata = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (json.dumps(metadata), task_id)
                )

                # S9: audit
                self._audit(
                    cur,
                    task_id=str(task_id),
                    event="paused",
                    old_status=old_status,
                    new_status="paused",
                    actor=actor,
                    reason=reason,
                )

                conn.commit()

    # ------------------------------------------------------------------
    # S6 — Dynamic Priority Reordering
    # ------------------------------------------------------------------

    def reprioritize(
        self,
        task_id: str,
        new_priority: str,
        actor: str = "hermes",
    ) -> bool:
        """
        S6: Change the priority of a queued (or paused) task.

        Args:
            task_id: Task UUID
            new_priority: One of 'critical', 'high', 'normal', 'low'
            actor: Who triggered the change (for audit)

        Returns:
            True if updated, False if task not found or priority invalid
        """
        if new_priority not in self.PRIORITY_REVERSE:
            log.warning("reprioritize: invalid priority %r for task %s", new_priority, task_id)
            return False

        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Fetch current inbox priority for audit
                cur.execute(
                    """
                    SELECT i.priority, t.status
                    FROM agent_tasks t
                    LEFT JOIN agent_inbox i ON i.active_task_id = t.id
                    WHERE t.id = %s
                    """,
                    (task_id,)
                )
                row = cur.fetchone()
                if not row:
                    return False

                old_priority = row[0]
                task_status = row[1]

                # Update inbox priority
                updated = cur.execute(
                    """
                    UPDATE agent_inbox
                    SET priority = %s
                    WHERE active_task_id = %s
                    """,
                    (new_priority, task_id)
                )

                # S9: audit
                self._audit(
                    cur,
                    task_id=str(task_id),
                    event="reprioritized",
                    old_status=task_status,
                    new_status=task_status,  # status unchanged
                    actor=actor,
                    extra={
                        "old_priority": old_priority,
                        "new_priority": new_priority,
                    },
                )

                conn.commit()
                log.info(
                    "reprioritize: task_id=%s %s→%s (actor=%s)",
                    task_id, old_priority, new_priority, actor,
                )
                return True

    # ------------------------------------------------------------------
    # S8 — Queue Metrics / Monitoring Dashboard
    # ------------------------------------------------------------------

    def queue_metrics(self) -> Dict[str, Any]:
        """
        S8: Return detailed queue statistics.

        Returns a dict with:
          - by_status: counts per task status
          - by_priority: counts of queued tasks per priority
          - stuck_running: tasks in 'running' status for > 30 minutes
          - pending_retry: tasks queued with a future retry_after
          - queue_depth: alias for by_status['queued']
          - total: total task count
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Counts per status
                cur.execute(
                    """
                    SELECT status, COUNT(*) FROM agent_tasks
                    GROUP BY status
                    """
                )
                by_status: Dict[str, int] = {row[0]: row[1] for row in cur.fetchall()}

                # Queued tasks by priority (from inbox join)
                cur.execute(
                    """
                    SELECT i.priority, COUNT(*)
                    FROM agent_tasks t
                    LEFT JOIN agent_inbox i ON i.active_task_id = t.id
                    WHERE t.status = 'queued'
                      AND (t.retry_after IS NULL OR t.retry_after <= NOW())
                    GROUP BY i.priority
                    """
                )
                by_priority: Dict[str, int] = {
                    (row[0] or "unknown"): row[1] for row in cur.fetchall()
                }

                # Stuck running tasks (> 30 min)
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM agent_tasks
                    WHERE status = 'running'
                      AND updated_at < NOW() - interval '30 minutes'
                    """
                )
                stuck_running: int = cur.fetchone()[0]

                # Tasks scheduled for future retry
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM agent_tasks
                    WHERE status = 'queued'
                      AND retry_after IS NOT NULL
                      AND retry_after > NOW()
                    """
                )
                pending_retry: int = cur.fetchone()[0]

                # Next scheduled retry time
                cur.execute(
                    """
                    SELECT MIN(retry_after)
                    FROM agent_tasks
                    WHERE status = 'queued'
                      AND retry_after > NOW()
                    """
                )
                next_retry_row = cur.fetchone()
                next_retry_at = (
                    next_retry_row[0].isoformat() if next_retry_row and next_retry_row[0]
                    else None
                )

                total = sum(by_status.values())

                return {
                    "by_status": by_status,
                    "by_priority": by_priority,
                    "stuck_running": stuck_running,
                    "pending_retry": pending_retry,
                    "next_retry_at": next_retry_at,
                    "queue_depth": by_status.get("queued", 0),
                    "total": total,
                    "snapshot_at": datetime.utcnow().isoformat() + "Z",
                }

    # ------------------------------------------------------------------
    # S9 — Audit Trail Read
    # ------------------------------------------------------------------

    def get_audit_trail(
        self,
        task_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """
        S9: Read audit log entries.

        Args:
            task_id: Filter by task UUID (None = all recent events)
            limit: Max rows to return

        Returns:
            List of audit log dicts, newest first
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if task_id:
                    cur.execute(
                        """
                        SELECT * FROM task_audit_log
                        WHERE task_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (str(task_id), limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM task_audit_log
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                rows = cur.fetchall()
                result = []
                for row in rows:
                    d = dict(row)
                    d['payload'] = _parse_jsonb(d.get('payload'))
                    if d.get('created_at'):
                        d['created_at'] = d['created_at'].isoformat()
                    result.append(d)
                return result

    # ------------------------------------------------------------------
    # Legacy helpers (kept for compatibility)
    # ------------------------------------------------------------------

    def get_queue_depth(self) -> int:
        """Get number of immediately-runnable queued tasks (respects retry_after)."""
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM agent_tasks
                    WHERE status = 'queued'
                      AND (retry_after IS NULL OR retry_after <= NOW())
                    """
                )
                return cur.fetchone()[0]

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get task status."""
        with get_db_connection(self.dbname) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        t.*,
                        i.raw_text as message_text,
                        i.source,
                        i.priority as priority_text
                    FROM agent_tasks t
                    LEFT JOIN agent_inbox i ON i.active_task_id = t.id
                    WHERE t.id = %s
                    """,
                    (task_id,)
                )
                task = cur.fetchone()
                if not task:
                    return None

                task_dict = dict(task)
                task_dict['metadata'] = _parse_jsonb(task_dict.get('metadata'))

                # Convert UUID strings to UUID objects
                if 'id' in task_dict and isinstance(task_dict['id'], str):
                    task_dict['id'] = uuid.UUID(task_dict['id'])

                # Extract data from metadata
                task_dict['task_data'] = task_dict['metadata'].get('task_data', {})
                task_dict['task_type'] = task_dict['metadata'].get('task_type', 'unknown')
                task_dict['checkpoint_data'] = task_dict['metadata'].get('checkpoint_data')

                # Map priority
                task_dict['priority'] = self.PRIORITY_REVERSE.get(
                    task_dict.get('priority_text', 'normal'), 5
                )

                return task_dict


if __name__ == "__main__":
    # Quick smoke test
    orchestrator = TaskOrchestrator()

    # Enqueue test message
    inbox_id = orchestrator.enqueue(
        message="Test task queue v2",
        source="manual",
        priority=5
    )
    print(f"Created inbox entry: {inbox_id}")

    # Create task
    task_id = orchestrator.create_task(
        inbox_id=inbox_id,
        task_type="test",
        task_data={"action": "test_queue", "title": "Test Task"}
    )
    print(f"Created task: {task_id}")

    # Dequeue
    task = orchestrator.dequeue()
    print(f"Dequeued task: {task['id']}")

    # Checkpoint
    orchestrator.checkpoint(task_id, {"step": 1, "progress": 50})
    print("Checkpoint saved")

    # Complete
    orchestrator.complete(task_id)
    print("Task completed")

    # Queue metrics (S8)
    metrics = orchestrator.queue_metrics()
    print(f"Metrics: {metrics}")

    # Audit trail (S9)
    trail = orchestrator.get_audit_trail(task_id=task_id, limit=10)
    print(f"Audit trail ({len(trail)} entries):")
    for entry in trail:
        print(f"  {entry['created_at']} {entry['event']} {entry.get('old_status')}→{entry.get('new_status')}")
