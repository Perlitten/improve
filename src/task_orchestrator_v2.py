#!/usr/bin/env python3
"""
Task Orchestrator V2: Adapted for production UUID schema.
Phase 1, Day 2: Stop losing work on restart.

This version works with the existing production schema:
- UUID-based IDs instead of SERIAL
- agent_inbox.active_task_id → agent_tasks.id relationship
- Production column names (raw_text, title, etc.)
"""

import json
import psycopg2
import psycopg2.extras
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
from contextlib import contextmanager
import uuid


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
    - Priority-based dequeue
    - Retry logic
    - Status tracking
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
    
    def __init__(self, dbname: str = "rag"):
        self.dbname = dbname
    
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
                
                conn.commit()
                return str(task_id)
    
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
                    SELECT 
                        t.*,
                        i.raw_text as message_text,
                        i.source,
                        i.priority as priority_text,
                        i.metadata as inbox_metadata
                    FROM agent_tasks t
                    LEFT JOIN agent_inbox i ON i.active_task_id = t.id
                    WHERE t.status = 'queued'
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
                
                conn.commit()
    
    def fail(self, task_id: str, error_message: str, should_retry: bool = True) -> None:
        """
        Mark task as failed.
        
        Args:
            task_id: Task UUID
            error_message: Error description
            should_retry: Whether to retry task
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
                retry_count = metadata.get('retry_count', 0)
                max_retries = metadata.get('max_retries', 3)
                
                # Check if should retry
                if should_retry and retry_count < max_retries:
                    # Increment retry count and requeue
                    metadata['retry_count'] = retry_count + 1
                    metadata['last_error'] = error_message
                    
                    cur.execute(
                        """
                        UPDATE agent_tasks
                        SET status = 'queued',
                            metadata = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (json.dumps(metadata), task_id)
                    )
                else:
                    # Mark as failed
                    metadata['last_error'] = error_message
                    
                    cur.execute(
                        """
                        UPDATE agent_tasks
                        SET status = 'failed',
                            metadata = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (json.dumps(metadata), task_id)
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
                
                conn.commit()
    
    def pause(self, task_id: str, reason: str) -> None:
        """
        Pause a running task.
        
        Args:
            task_id: Task UUID
            reason: Reason for pausing
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
                conn.commit()
    
    def get_queue_depth(self) -> int:
        """Get number of queued tasks."""
        with get_db_connection(self.dbname) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM agent_tasks WHERE status = 'queued'")
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
    # Test
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
    
    # Check queue depth
    depth = orchestrator.get_queue_depth()
    print(f"Queue depth: {depth}")
