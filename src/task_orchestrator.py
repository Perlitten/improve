#!/usr/bin/env python3
"""
Task Orchestrator: Persistent task queue with checkpoint/resume.
Phase 1, Day 2: Stop losing work on restart.
"""

import json
import psycopg2
import psycopg2.extras
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
from contextlib import contextmanager


@contextmanager
def get_db_connection(dbname: str = "rag"):
    """Get database connection with automatic cleanup."""
    try:
        # Try to use unified config
        from config_loader import get_config
        config = get_config()
        
        conn = psycopg2.connect(
            host=config.get('database.host', '127.0.0.1'),
            port=config.get('database.port', 5432),
            dbname=config.get('database.name', dbname),
            user=config.get('database.user'),
            password=config.get('database.password'),
        )
    except (ImportError, FileNotFoundError, ValueError):
        # Fallback to old method if config not available
        env_path = Path.home() / ".hermes/automation.env"
        env = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip()
        
        conn = psycopg2.connect(
            host="127.0.0.1",
            port=5432,
            dbname=dbname,
            user=env.get("POSTGRES_USER", "automation"),
            password=env.get("POSTGRES_PASSWORD", ""),
        )
    
    try:
        yield conn
    finally:
        conn.close()


class TaskOrchestrator:
    """
    Persistent task queue with checkpoint/resume support.
    
    Features:
    - Tasks survive restarts
    - Checkpoint/resume for long-running tasks
    - Priority-based dequeue
    - Retry logic
    - Status tracking
    """
    
    def __init__(self, dbname: str = "rag"):
        self.dbname = dbname
    
    def enqueue(
        self,
        message: str,
        source: str,
        priority: int = 5,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Enqueue a new message to inbox.
        
        Args:
            message: Message text
            source: Source of message (telegram, n8n, api, etc.)
            priority: Priority 1-10 (1=highest)
            metadata: Additional context
        
        Returns:
            inbox_id: ID of created inbox entry
        """
        if not 1 <= priority <= 10:
            raise ValueError("Priority must be between 1 and 10")
        
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_inbox (message_text, source, priority, metadata)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (message, source, priority, json.dumps(metadata or {}))
                )
                inbox_id = cur.fetchone()[0]
                conn.commit()
                return inbox_id
    
    def create_task(
        self,
        inbox_id: int,
        task_type: str,
        task_data: Dict,
        max_retries: int = 3
    ) -> int:
        """
        Create a task from inbox entry.
        
        Args:
            inbox_id: Reference to inbox entry
            task_type: Type of task (code_fix, analysis, etc.)
            task_data: Task-specific data
            max_retries: Maximum retry attempts
        
        Returns:
            task_id: ID of created task
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_tasks (inbox_id, task_type, task_data, max_retries)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (inbox_id, task_type, json.dumps(task_data), max_retries)
                )
                task_id = cur.fetchone()[0]
                conn.commit()
                return task_id
    
    def dequeue(self) -> Optional[Dict]:
        """
        Dequeue next task by priority.
        
        Returns:
            Task dict or None if queue empty
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get highest priority queued task
                cur.execute(
                    """
                    SELECT t.*, i.message_text, i.source, i.priority, i.metadata as inbox_metadata
                    FROM agent_tasks t
                    JOIN agent_inbox i ON t.inbox_id = i.id
                    WHERE t.status = 'queued'
                    ORDER BY i.priority ASC, t.id ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
                task = cur.fetchone()
                
                if not task:
                    return None
                
                # Mark as running
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = 'running', started_at = NOW()
                    WHERE id = %s
                    """,
                    (task['id'],)
                )
                
                # Mark inbox as processing
                cur.execute(
                    """
                    UPDATE agent_inbox
                    SET status = 'processing', processed_at = NOW()
                    WHERE id = %s
                    """,
                    (task['inbox_id'],)
                )
                
                conn.commit()
                
                # Convert to dict and parse JSON fields
                task_dict = dict(task)
                task_dict['task_data'] = json.loads(task_dict['task_data']) if task_dict['task_data'] else {}
                task_dict['checkpoint_data'] = json.loads(task_dict['checkpoint_data']) if task_dict['checkpoint_data'] else None
                task_dict['inbox_metadata'] = json.loads(task_dict['inbox_metadata']) if task_dict['inbox_metadata'] else {}
                
                return task_dict
    
    def checkpoint(self, task_id: int, state: Dict) -> None:
        """
        Save checkpoint for task.
        
        Args:
            task_id: Task ID
            state: State to save
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET checkpoint_data = %s
                    WHERE id = %s
                    """,
                    (json.dumps(state), task_id)
                )
                conn.commit()
    
    def resume(self, task_id: int) -> Optional[Dict]:
        """
        Resume a paused task.
        
        Args:
            task_id: Task ID
        
        Returns:
            Task dict with checkpoint data or None
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT t.*, i.message_text, i.source, i.priority, i.metadata as inbox_metadata
                    FROM agent_tasks t
                    JOIN agent_inbox i ON t.inbox_id = i.id
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
                    SET status = 'running'
                    WHERE id = %s
                    """,
                    (task_id,)
                )
                conn.commit()
                
                # Convert to dict and parse JSON fields
                task_dict = dict(task)
                task_dict['task_data'] = json.loads(task_dict['task_data']) if task_dict['task_data'] else {}
                task_dict['checkpoint_data'] = json.loads(task_dict['checkpoint_data']) if task_dict['checkpoint_data'] else None
                task_dict['inbox_metadata'] = json.loads(task_dict['inbox_metadata']) if task_dict['inbox_metadata'] else {}
                
                return task_dict
    
    def complete(self, task_id: int, result: Optional[Dict] = None) -> None:
        """
        Mark task as completed.
        
        Args:
            task_id: Task ID
            result: Optional result data
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Update task
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = 'completed', completed_at = NOW()
                    WHERE id = %s
                    RETURNING inbox_id
                    """,
                    (task_id,)
                )
                row = cur.fetchone()
                if not row:
                    return
                
                inbox_id = row[0]
                
                # Check if all tasks for this inbox are completed
                cur.execute(
                    """
                    SELECT COUNT(*) FROM agent_tasks
                    WHERE inbox_id = %s AND status NOT IN ('completed', 'failed')
                    """,
                    (inbox_id,)
                )
                pending_count = cur.fetchone()[0]
                
                # If all tasks done, mark inbox as completed
                if pending_count == 0:
                    cur.execute(
                        """
                        UPDATE agent_inbox
                        SET status = 'completed'
                        WHERE id = %s
                        """,
                        (inbox_id,)
                    )
                
                conn.commit()
    
    def fail(self, task_id: int, error_message: str, should_retry: bool = True) -> None:
        """
        Mark task as failed.
        
        Args:
            task_id: Task ID
            error_message: Error description
            should_retry: Whether to retry task
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                # Get current retry count and max retries
                cur.execute(
                    """
                    SELECT retry_count, max_retries FROM agent_tasks
                    WHERE id = %s
                    """,
                    (task_id,)
                )
                row = cur.fetchone()
                if not row:
                    return
                
                retry_count, max_retries = row
                
                # Check if should retry
                if should_retry and retry_count < max_retries:
                    # Increment retry count and requeue
                    cur.execute(
                        """
                        UPDATE agent_tasks
                        SET status = 'queued',
                            retry_count = retry_count + 1,
                            error_message = %s
                        WHERE id = %s
                        """,
                        (error_message, task_id)
                    )
                else:
                    # Mark as failed
                    cur.execute(
                        """
                        UPDATE agent_tasks
                        SET status = 'failed',
                            completed_at = NOW(),
                            error_message = %s
                        WHERE id = %s
                        RETURNING inbox_id
                        """,
                        (error_message, task_id)
                    )
                    row = cur.fetchone()
                    if row:
                        inbox_id = row[0]
                        
                        # Mark inbox as failed if all tasks failed
                        cur.execute(
                            """
                            SELECT COUNT(*) FROM agent_tasks
                            WHERE inbox_id = %s AND status NOT IN ('completed', 'failed')
                            """,
                            (inbox_id,)
                        )
                        pending_count = cur.fetchone()[0]
                        
                        if pending_count == 0:
                            cur.execute(
                                """
                                UPDATE agent_inbox
                                SET status = 'failed'
                                WHERE id = %s
                                """,
                                (inbox_id,)
                            )
                
                conn.commit()
    
    def pause(self, task_id: int, reason: str) -> None:
        """
        Pause a running task.
        
        Args:
            task_id: Task ID
            reason: Reason for pausing
        """
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = 'paused', error_message = %s
                    WHERE id = %s
                    """,
                    (reason, task_id)
                )
                conn.commit()
    
    def get_queue_depth(self) -> int:
        """Get number of queued tasks."""
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM agent_tasks WHERE status = 'queued'")
                return cur.fetchone()[0]
    
    def get_task_status(self, task_id: int) -> Optional[Dict]:
        """Get task status."""
        with get_db_connection(self.dbname) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT t.*, i.message_text, i.source, i.priority
                    FROM agent_tasks t
                    JOIN agent_inbox i ON t.inbox_id = i.id
                    WHERE t.id = %s
                    """,
                    (task_id,)
                )
                task = cur.fetchone()
                if not task:
                    return None
                
                task_dict = dict(task)
                task_dict['task_data'] = json.loads(task_dict['task_data']) if task_dict['task_data'] else {}
                task_dict['checkpoint_data'] = json.loads(task_dict['checkpoint_data']) if task_dict['checkpoint_data'] else None
                
                return task_dict


if __name__ == "__main__":
    # Test
    orchestrator = TaskOrchestrator()
    
    # Enqueue test message
    inbox_id = orchestrator.enqueue(
        message="Test task queue",
        source="manual",
        priority=5
    )
    print(f"Created inbox entry: {inbox_id}")
    
    # Create task
    task_id = orchestrator.create_task(
        inbox_id=inbox_id,
        task_type="test",
        task_data={"action": "test_queue"}
    )
    print(f"Created task: {task_id}")
    
    # Dequeue
    task = orchestrator.dequeue()
    print(f"Dequeued task: {task}")
    
    # Checkpoint
    orchestrator.checkpoint(task_id, {"step": 1, "progress": 50})
    print("Checkpoint saved")
    
    # Complete
    orchestrator.complete(task_id)
    print("Task completed")
    
    # Check queue depth
    depth = orchestrator.get_queue_depth()
    print(f"Queue depth: {depth}")
