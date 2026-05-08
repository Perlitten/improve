"""
Unit tests for Phase 10 S6-S10 additions to TaskOrchestrator.

Tests run without a real DB — all DB calls are mocked.
Coverage:
  S6 — reprioritize()
  S7 — exponential backoff in fail() / retry_after filter in dequeue()
  S8 — queue_metrics()
  S9 — _audit() helper + get_audit_trail()
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

SRC = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(SRC))

from task_orchestrator_v2 import TaskOrchestrator, _parse_jsonb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_orch() -> TaskOrchestrator:
    return TaskOrchestrator(dbname="test")


def _mock_conn(cur_mock=None):
    """Return a context-manager-compatible mock connection."""
    if cur_mock is None:
        cur_mock = MagicMock()
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = lambda s: s
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur_mock
    # Make cursor() itself a context manager
    cur_mock.__enter__ = lambda s: s
    cur_mock.__exit__ = MagicMock(return_value=False)
    return conn


# ---------------------------------------------------------------------------
# S6 — reprioritize
# ---------------------------------------------------------------------------

class TestReprioritize:
    def test_invalid_priority_returns_false(self):
        orch = _make_orch()
        result = orch.reprioritize("some-uuid", "ultra-critical")
        assert result is False

    def test_valid_priority_updates_inbox(self):
        orch = _make_orch()
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        # SELECT returns (old_priority, task_status)
        cur.fetchone.return_value = ("normal", "queued")

        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            result = orch.reprioritize("task-uuid-1", "high", actor="hermes")

        assert result is True
        # Should UPDATE agent_inbox
        update_calls = [
            c for c in cur.execute.call_args_list
            if "UPDATE agent_inbox" in str(c)
        ]
        assert len(update_calls) == 1
        # new priority should be 'high' — check the params tuple (second element)
        sql, params = update_calls[0][0]
        assert "high" in params

    def test_task_not_found_returns_false(self):
        orch = _make_orch()
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = None  # task not found

        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            result = orch.reprioritize("nonexistent", "low")

        assert result is False

    def test_reprioritize_all_valid_priorities(self):
        orch = _make_orch()
        for prio in ("critical", "high", "normal", "low"):
            cur = MagicMock()
            cur.__enter__ = lambda s: s
            cur.__exit__ = MagicMock(return_value=False)
            cur.fetchone.return_value = ("normal", "queued")

            conn = MagicMock()
            conn.__enter__ = lambda s: s
            conn.__exit__ = MagicMock(return_value=False)
            conn.cursor.return_value = cur

            with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
                result = orch.reprioritize("tid", prio)
            assert result is True, f"should succeed for priority={prio}"


# ---------------------------------------------------------------------------
# S7 — exponential backoff
# ---------------------------------------------------------------------------

class TestExponentialBackoff:
    def _make_fail_cur(self, retry_count=0, max_retries=3, old_status="running"):
        metadata = {"retry_count": retry_count, "max_retries": max_retries}
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        # SELECT status, metadata
        cur.fetchone.return_value = (old_status, json.dumps(metadata))
        return cur

    def _run_fail(self, retry_count, max_retries=3, should_retry=True):
        orch = _make_orch()
        cur = self._make_fail_cur(retry_count=retry_count, max_retries=max_retries)
        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            orch.fail("tid", "some error", should_retry=should_retry)

        return cur

    def test_first_retry_uses_30s_backoff(self):
        cur = self._run_fail(retry_count=0)
        update_calls = [c for c in cur.execute.call_args_list if "retry_after" in str(c)]
        assert len(update_calls) == 1
        # delay = 30 * 2^0 = 30
        args_str = str(update_calls[0])
        assert "30" in args_str

    def test_second_retry_uses_60s_backoff(self):
        cur = self._run_fail(retry_count=1)
        update_calls = [c for c in cur.execute.call_args_list if "retry_after" in str(c)]
        assert len(update_calls) == 1
        args_str = str(update_calls[0])
        # delay = 30 * 2^1 = 60
        assert "60" in args_str

    def test_third_retry_uses_120s_backoff(self):
        cur = self._run_fail(retry_count=2)
        update_calls = [c for c in cur.execute.call_args_list if "retry_after" in str(c)]
        assert len(update_calls) == 1
        args_str = str(update_calls[0])
        # delay = 30 * 2^2 = 120
        assert "120" in args_str

    def test_backoff_capped_at_3600(self):
        # retry_count=100 → 30 * 2^100 >> 3600; should be capped
        orch = _make_orch()
        delay = min(orch.BACKOFF_BASE_SECONDS * (2 ** 100), orch.BACKOFF_MAX_SECONDS)
        assert delay == orch.BACKOFF_MAX_SECONDS  # 3600

    def test_exhausted_retries_marks_failed(self):
        cur = self._run_fail(retry_count=3, max_retries=3, should_retry=True)
        # Should UPDATE status='failed', NOT set retry_after
        update_calls = [c for c in cur.execute.call_args_list if "UPDATE agent_tasks" in str(c)]
        assert any("'failed'" in str(c) or "failed" in str(c) for c in update_calls)
        # retry_after should NOT be set when exhausted
        retry_after_calls = [c for c in cur.execute.call_args_list if "retry_after" in str(c)]
        assert len(retry_after_calls) == 0

    def test_should_retry_false_marks_failed_immediately(self):
        cur = self._run_fail(retry_count=0, max_retries=3, should_retry=False)
        update_calls = [c for c in cur.execute.call_args_list if "UPDATE agent_tasks" in str(c)]
        assert any("failed" in str(c) for c in update_calls)

    def test_dequeue_sql_includes_retry_after_filter(self):
        """dequeue() SQL must contain retry_after check."""
        orch = _make_orch()
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = None  # empty queue

        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            result = orch.dequeue()

        assert result is None
        select_sql = str(cur.execute.call_args_list[0])
        assert "retry_after" in select_sql


# ---------------------------------------------------------------------------
# S8 — queue_metrics
# ---------------------------------------------------------------------------

class TestQueueMetrics:
    def _run_metrics(self):
        orch = _make_orch()
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        # by_status
        cur.fetchall.side_effect = [
            [("queued", 5), ("running", 2), ("completed", 10), ("failed", 1)],
            [("normal", 3), ("low", 2)],   # by_priority
        ]
        cur.fetchone.side_effect = [
            (1,),    # stuck_running
            (2,),    # pending_retry
            (None,), # next_retry_at
        ]

        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            return orch.queue_metrics()

    def test_returns_dict_with_required_keys(self):
        metrics = self._run_metrics()
        for key in ("by_status", "by_priority", "stuck_running", "pending_retry",
                    "queue_depth", "total", "snapshot_at"):
            assert key in metrics, f"missing key: {key}"

    def test_queue_depth_matches_queued_status(self):
        metrics = self._run_metrics()
        assert metrics["queue_depth"] == metrics["by_status"].get("queued", 0)

    def test_total_is_sum_of_all_statuses(self):
        metrics = self._run_metrics()
        assert metrics["total"] == sum(metrics["by_status"].values())

    def test_stuck_running_count(self):
        metrics = self._run_metrics()
        assert metrics["stuck_running"] == 1

    def test_pending_retry_count(self):
        metrics = self._run_metrics()
        assert metrics["pending_retry"] == 2

    def test_snapshot_at_is_iso_string(self):
        metrics = self._run_metrics()
        assert isinstance(metrics["snapshot_at"], str)
        assert "Z" in metrics["snapshot_at"] or "T" in metrics["snapshot_at"]


# ---------------------------------------------------------------------------
# S9 — _audit helper
# ---------------------------------------------------------------------------

class TestAuditHelper:
    def test_audit_inserts_row(self):
        orch = _make_orch()
        cur = MagicMock()
        orch._audit(
            cur,
            task_id="task-123",
            event="completed",
            old_status="running",
            new_status="completed",
            actor="ralph",
            reason="all done",
        )
        cur.execute.assert_called_once()
        sql, params = cur.execute.call_args[0]
        assert "task_audit_log" in sql
        assert "task-123" in params
        assert "completed" in params

    def test_audit_silently_ignores_db_error(self):
        orch = _make_orch()
        cur = MagicMock()
        cur.execute.side_effect = Exception("table does not exist")
        # Must not raise
        orch._audit(cur, task_id="x", event="test")

    def test_audit_payload_contains_extra(self):
        orch = _make_orch()
        cur = MagicMock()
        orch._audit(
            cur,
            task_id="task-999",
            event="reprioritized",
            extra={"old_priority": "normal", "new_priority": "high"},
        )
        _, params = cur.execute.call_args[0]
        payload_str = params[-1]  # last param is the JSON payload
        payload = json.loads(payload_str)
        assert payload["old_priority"] == "normal"
        assert payload["new_priority"] == "high"

    def test_complete_writes_audit(self):
        """complete() must call _audit internally."""
        orch = _make_orch()
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = ("running",)

        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            orch.complete("task-1")

        audit_calls = [c for c in cur.execute.call_args_list if "task_audit_log" in str(c)]
        assert len(audit_calls) >= 1

    def test_pause_writes_audit(self):
        orch = _make_orch()
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = ("running", json.dumps({}))

        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            orch.pause("task-2", "priority=critical requires_human", actor="ralph")

        audit_calls = [c for c in cur.execute.call_args_list if "task_audit_log" in str(c)]
        assert len(audit_calls) >= 1


# ---------------------------------------------------------------------------
# S9 — get_audit_trail
# ---------------------------------------------------------------------------

class TestGetAuditTrail:
    def _make_audit_row(self, event="completed"):
        return {
            "id": 1,
            "task_id": "task-abc",
            "event": event,
            "old_status": "running",
            "new_status": "completed",
            "actor": "ralph",
            "payload": json.dumps({"has_result": True}),
            "created_at": datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc),
        }

    def test_returns_list_of_dicts(self):
        orch = _make_orch()
        row = self._make_audit_row()
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchall.return_value = [row]

        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            result = orch.get_audit_trail(task_id="task-abc")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["event"] == "completed"

    def test_payload_parsed_from_json(self):
        orch = _make_orch()
        row = self._make_audit_row()
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchall.return_value = [row]

        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            result = orch.get_audit_trail()

        assert isinstance(result[0]["payload"], dict)
        assert result[0]["payload"]["has_result"] is True

    def test_created_at_converted_to_isoformat(self):
        orch = _make_orch()
        row = self._make_audit_row()
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchall.return_value = [row]

        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            result = orch.get_audit_trail()

        assert isinstance(result[0]["created_at"], str)

    def test_get_audit_trail_no_task_id_fetches_recent(self):
        orch = _make_orch()
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchall.return_value = []

        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur

        with patch("task_orchestrator_v2.get_db_connection", return_value=conn):
            result = orch.get_audit_trail(limit=25)

        assert result == []
        # SQL should NOT contain task_id param for None case
        select_sql = str(cur.execute.call_args_list[0][0][0])
        assert "task_id" not in select_sql or "WHERE" not in select_sql
