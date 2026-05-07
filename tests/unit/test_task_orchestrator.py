"""Unit tests for task_orchestrator.py"""

import pytest
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from task_orchestrator import TaskOrchestrator


@pytest.mark.unit
class TestTaskOrchestrator:
    """Test task orchestrator functionality"""
    
    def test_enqueue_creates_inbox_entry(self, orchestrator, db_connection):
        """Test enqueue creates inbox entry"""
        inbox_id = orchestrator.enqueue(
            message="Test message",
            source="test",
            priority=5
        )
        
        assert inbox_id > 0
        
        # Verify in database
        with db_connection.cursor() as cur:
            cur.execute("SELECT * FROM agent_inbox WHERE id = %s", (inbox_id,))
            row = cur.fetchone()
            assert row is not None
            assert row[1] == "Test message"  # message_text
            assert row[2] == "test"  # source
            assert row[3] == 5  # priority
    
    def test_enqueue_with_metadata(self, orchestrator, db_connection):
        """Test enqueue with metadata"""
        metadata = {"user": "test_user", "context": "testing"}
        inbox_id = orchestrator.enqueue(
            message="Test with metadata",
            source="test",
            priority=3,
            metadata=metadata
        )
        
        assert inbox_id > 0
        
        # Verify metadata stored
        with db_connection.cursor() as cur:
            cur.execute("SELECT metadata FROM agent_inbox WHERE id = %s", (inbox_id,))
            stored_metadata = cur.fetchone()[0]
            assert stored_metadata["user"] == "test_user"
            assert stored_metadata["context"] == "testing"
    
    def test_enqueue_invalid_priority_raises_error(self, orchestrator):
        """Test enqueue with invalid priority raises error"""
        with pytest.raises(ValueError, match="Priority must be between 1 and 10"):
            orchestrator.enqueue(
                message="Test",
                source="test",
                priority=11  # Invalid
            )
    
    def test_create_task(self, orchestrator, db_connection):
        """Test create_task creates task entry"""
        # Create inbox first
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        
        # Create task
        task_id = orchestrator.create_task(
            inbox_id=inbox_id,
            task_type="test_task",
            task_data={"action": "test"}
        )
        
        assert task_id > 0
        
        # Verify in database
        with db_connection.cursor() as cur:
            cur.execute("SELECT * FROM agent_tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            assert row is not None
            assert row[1] == inbox_id  # inbox_id
            assert row[2] == "test_task"  # task_type
            assert row[4] == "queued"  # status
    
    def test_dequeue_returns_highest_priority(self, orchestrator):
        """Test dequeue returns highest priority task"""
        # Create tasks with different priorities
        inbox_id_low = orchestrator.enqueue("Low priority", "test", priority=8)
        inbox_id_high = orchestrator.enqueue("High priority", "test", priority=2)
        inbox_id_mid = orchestrator.enqueue("Mid priority", "test", priority=5)
        
        task_id_low = orchestrator.create_task(inbox_id_low, "test", {})
        task_id_high = orchestrator.create_task(inbox_id_high, "test", {})
        task_id_mid = orchestrator.create_task(inbox_id_mid, "test", {})
        
        # Dequeue should return highest priority (lowest number)
        task = orchestrator.dequeue()
        
        assert task is not None
        assert task['id'] == task_id_high
        assert task['priority'] == 2
    
    def test_dequeue_empty_queue_returns_none(self, orchestrator):
        """Test dequeue on empty queue returns None"""
        task = orchestrator.dequeue()
        assert task is None
    
    def test_dequeue_marks_task_as_running(self, orchestrator, db_connection):
        """Test dequeue marks task as running"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {})
        
        task = orchestrator.dequeue()
        
        # Verify status changed to running
        with db_connection.cursor() as cur:
            cur.execute("SELECT status FROM agent_tasks WHERE id = %s", (task_id,))
            status = cur.fetchone()[0]
            assert status == "running"
    
    def test_checkpoint_saves_state(self, orchestrator, db_connection):
        """Test checkpoint saves state"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {})
        
        state = {"step": 3, "progress": 75, "data": "test_data"}
        orchestrator.checkpoint(task_id, state)
        
        # Verify checkpoint saved
        with db_connection.cursor() as cur:
            cur.execute("SELECT checkpoint_data FROM agent_tasks WHERE id = %s", (task_id,))
            checkpoint = cur.fetchone()[0]
            assert checkpoint["step"] == 3
            assert checkpoint["progress"] == 75
            assert checkpoint["data"] == "test_data"
    
    def test_resume_paused_task(self, orchestrator, db_connection):
        """Test resume returns paused task with checkpoint"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {})
        
        # Pause task
        orchestrator.pause(task_id, "Testing pause")
        
        # Save checkpoint
        state = {"step": 2, "progress": 50}
        orchestrator.checkpoint(task_id, state)
        
        # Resume
        task = orchestrator.resume(task_id)
        
        assert task is not None
        assert task['id'] == task_id
        assert task['status'] == "running"
        assert task['checkpoint_data']['step'] == 2
        assert task['checkpoint_data']['progress'] == 50
    
    def test_resume_non_paused_task_returns_none(self, orchestrator):
        """Test resume on non-paused task returns None"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {})
        
        # Task is queued, not paused
        task = orchestrator.resume(task_id)
        assert task is None
    
    def test_complete_marks_task_completed(self, orchestrator, db_connection):
        """Test complete marks task as completed"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {})
        
        orchestrator.complete(task_id)
        
        # Verify status
        with db_connection.cursor() as cur:
            cur.execute("SELECT status, completed_at FROM agent_tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            assert row[0] == "completed"
            assert row[1] is not None  # completed_at set
    
    def test_complete_marks_inbox_completed(self, orchestrator, db_connection):
        """Test complete marks inbox as completed when all tasks done"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {})
        
        orchestrator.complete(task_id)
        
        # Verify inbox status
        with db_connection.cursor() as cur:
            cur.execute("SELECT status FROM agent_inbox WHERE id = %s", (inbox_id,))
            status = cur.fetchone()[0]
            assert status == "completed"
    
    def test_fail_with_retry(self, orchestrator, db_connection):
        """Test fail with retry requeues task"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {}, max_retries=3)
        
        orchestrator.fail(task_id, "Test error", should_retry=True)
        
        # Verify task requeued
        with db_connection.cursor() as cur:
            cur.execute("SELECT status, retry_count FROM agent_tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            assert row[0] == "queued"
            assert row[1] == 1  # retry_count incremented
    
    def test_fail_without_retry(self, orchestrator, db_connection):
        """Test fail without retry marks task as failed"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {})
        
        orchestrator.fail(task_id, "Test error", should_retry=False)
        
        # Verify task failed
        with db_connection.cursor() as cur:
            cur.execute("SELECT status, error_message FROM agent_tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            assert row[0] == "failed"
            assert row[1] == "Test error"
    
    def test_fail_max_retries_exceeded(self, orchestrator, db_connection):
        """Test fail after max retries marks task as failed"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {}, max_retries=2)
        
        # Fail 3 times (exceeds max_retries=2)
        orchestrator.fail(task_id, "Error 1", should_retry=True)
        orchestrator.fail(task_id, "Error 2", should_retry=True)
        orchestrator.fail(task_id, "Error 3", should_retry=True)
        
        # Verify task failed
        with db_connection.cursor() as cur:
            cur.execute("SELECT status, retry_count FROM agent_tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            assert row[0] == "failed"
            assert row[1] == 2  # max retries reached
    
    def test_pause_task(self, orchestrator, db_connection):
        """Test pause marks task as paused"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {})
        
        orchestrator.pause(task_id, "Testing pause")
        
        # Verify status
        with db_connection.cursor() as cur:
            cur.execute("SELECT status, error_message FROM agent_tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            assert row[0] == "paused"
            assert row[1] == "Testing pause"
    
    def test_get_queue_depth(self, orchestrator):
        """Test get_queue_depth returns correct count"""
        # Create multiple tasks
        for i in range(5):
            inbox_id = orchestrator.enqueue(f"Test {i}", "test", 5)
            orchestrator.create_task(inbox_id, "test", {})
        
        depth = orchestrator.get_queue_depth()
        assert depth == 5
    
    def test_get_queue_depth_excludes_running(self, orchestrator):
        """Test get_queue_depth excludes running tasks"""
        # Create tasks
        for i in range(3):
            inbox_id = orchestrator.enqueue(f"Test {i}", "test", 5)
            orchestrator.create_task(inbox_id, "test", {})
        
        # Dequeue one (marks as running)
        orchestrator.dequeue()
        
        depth = orchestrator.get_queue_depth()
        assert depth == 2  # Only queued tasks
    
    def test_get_task_status(self, orchestrator):
        """Test get_task_status returns task details"""
        inbox_id = orchestrator.enqueue("Test", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {"key": "value"})
        
        status = orchestrator.get_task_status(task_id)
        
        assert status is not None
        assert status['id'] == task_id
        assert status['task_type'] == "test"
        assert status['task_data']['key'] == "value"
        assert status['status'] == "queued"
    
    def test_get_task_status_nonexistent_returns_none(self, orchestrator):
        """Test get_task_status for nonexistent task returns None"""
        status = orchestrator.get_task_status(99999)
        assert status is None
    
    def test_task_survives_restart(self, orchestrator, db_connection):
        """Test task persists across orchestrator instances (simulated restart)"""
        # Create task
        inbox_id = orchestrator.enqueue("Test restart", "test", 5)
        task_id = orchestrator.create_task(inbox_id, "test", {"data": "persist"})
        
        # Save checkpoint
        orchestrator.checkpoint(task_id, {"step": 5})
        
        # Create new orchestrator instance (simulates restart)
        new_orchestrator = TaskOrchestrator()
        
        # Verify task still exists
        status = new_orchestrator.get_task_status(task_id)
        assert status is not None
        assert status['task_data']['data'] == "persist"
        assert status['checkpoint_data']['step'] == 5
    
    def test_multiple_tasks_same_inbox(self, orchestrator):
        """Test multiple tasks can reference same inbox"""
        inbox_id = orchestrator.enqueue("Parent message", "test", 5)
        
        task_id_1 = orchestrator.create_task(inbox_id, "subtask_1", {"sub": 1})
        task_id_2 = orchestrator.create_task(inbox_id, "subtask_2", {"sub": 2})
        
        # Both tasks should exist
        status_1 = orchestrator.get_task_status(task_id_1)
        status_2 = orchestrator.get_task_status(task_id_2)
        
        assert status_1['inbox_id'] == inbox_id
        assert status_2['inbox_id'] == inbox_id
        assert status_1['task_type'] == "subtask_1"
        assert status_2['task_type'] == "subtask_2"
    
    def test_inbox_not_completed_until_all_tasks_done(self, orchestrator, db_connection):
        """Test inbox stays processing until all tasks completed"""
        inbox_id = orchestrator.enqueue("Parent", "test", 5)
        
        task_id_1 = orchestrator.create_task(inbox_id, "task_1", {})
        task_id_2 = orchestrator.create_task(inbox_id, "task_2", {})
        
        # Complete first task
        orchestrator.complete(task_id_1)
        
        # Inbox should still be processing
        with db_connection.cursor() as cur:
            cur.execute("SELECT status FROM agent_inbox WHERE id = %s", (inbox_id,))
            status = cur.fetchone()[0]
            assert status != "completed"
        
        # Complete second task
        orchestrator.complete(task_id_2)
        
        # Now inbox should be completed
        with db_connection.cursor() as cur:
            cur.execute("SELECT status FROM agent_inbox WHERE id = %s", (inbox_id,))
            status = cur.fetchone()[0]
            assert status == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
