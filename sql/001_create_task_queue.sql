-- Task Queue Schema
-- Phase 1, Day 2: Task persistence and checkpoint/resume
-- Date: 2026-05-05

-- Agent Inbox: Incoming messages/requests
CREATE TABLE IF NOT EXISTS agent_inbox (
    id SERIAL PRIMARY KEY,
    message_text TEXT NOT NULL,
    source VARCHAR(50) NOT NULL,  -- 'telegram', 'n8n', 'api', 'cron', 'manual'
    priority INT DEFAULT 5,  -- 1=highest, 10=lowest
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb,  -- Additional context
    CONSTRAINT valid_priority CHECK (priority BETWEEN 1 AND 10),
    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
);

-- Agent Tasks: Decomposed work units
CREATE TABLE IF NOT EXISTS agent_tasks (
    id SERIAL PRIMARY KEY,
    inbox_id INT REFERENCES agent_inbox(id) ON DELETE CASCADE,
    task_type VARCHAR(50) NOT NULL,  -- 'code_fix', 'analysis', 'deployment', etc.
    task_data JSONB NOT NULL,  -- Task-specific data
    status VARCHAR(20) DEFAULT 'queued',  -- 'queued', 'running', 'paused', 'completed', 'failed'
    checkpoint_data JSONB,  -- State for resume
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    CONSTRAINT valid_task_status CHECK (status IN ('queued', 'running', 'paused', 'completed', 'failed'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_inbox_status_priority ON agent_inbox(status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON agent_tasks(status, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_inbox_id ON agent_tasks(inbox_id);

-- Comments for documentation
COMMENT ON TABLE agent_inbox IS 'Incoming messages and requests from various sources';
COMMENT ON TABLE agent_tasks IS 'Decomposed work units with checkpoint/resume support';
COMMENT ON COLUMN agent_inbox.priority IS '1=highest priority, 10=lowest priority';
COMMENT ON COLUMN agent_tasks.checkpoint_data IS 'State snapshot for resuming interrupted tasks';
