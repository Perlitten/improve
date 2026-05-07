-- Task Queue Schema
-- Migration: 001_task_queue
-- Date: 2026-05-05

-- Agent Inbox: Incoming messages/tasks
CREATE TABLE IF NOT EXISTS agent_inbox (
    id SERIAL PRIMARY KEY,
    message_text TEXT NOT NULL,
    source VARCHAR(50) NOT NULL,  -- telegram, api, cron, system
    priority INT DEFAULT 5,  -- 1 (highest) to 10 (lowest)
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Agent Tasks: Processed tasks with state
CREATE TABLE IF NOT EXISTS agent_tasks (
    id SERIAL PRIMARY KEY,
    inbox_id INT REFERENCES agent_inbox(id) ON DELETE CASCADE,
    task_type VARCHAR(50) NOT NULL,  -- question, command, tool_use, planning
    task_data JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'queued',  -- queued, running, paused, completed, failed
    checkpoint_data JSONB,
    
    -- Cost tracking
    cost_usd DECIMAL(10,4),
    model_used VARCHAR(100),
    tokens_used INT,
    
    -- Timing
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_seconds INT,
    
    -- Error handling
    error_message TEXT,
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    
    -- Result
    result_data JSONB,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_inbox_status_priority ON agent_inbox(status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_inbox_source ON agent_inbox(source);
CREATE INDEX IF NOT EXISTS idx_inbox_created ON agent_inbox(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON agent_tasks(status, started_at);
CREATE INDEX IF NOT EXISTS idx_tasks_inbox ON agent_tasks(inbox_id);
CREATE INDEX IF NOT EXISTS idx_tasks_type ON agent_tasks(task_type);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON agent_tasks(created_at DESC);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for agent_tasks
DROP TRIGGER IF EXISTS update_agent_tasks_updated_at ON agent_tasks;
CREATE TRIGGER update_agent_tasks_updated_at
    BEFORE UPDATE ON agent_tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- View for active tasks
CREATE OR REPLACE VIEW active_tasks AS
SELECT 
    t.id,
    t.task_type,
    t.status,
    t.model_used,
    t.cost_usd,
    t.started_at,
    EXTRACT(EPOCH FROM (NOW() - t.started_at)) as running_seconds,
    i.message_text,
    i.source,
    i.priority
FROM agent_tasks t
JOIN agent_inbox i ON i.id = t.inbox_id
WHERE t.status IN ('queued', 'running', 'paused')
ORDER BY i.priority, t.started_at;

-- View for task statistics
CREATE OR REPLACE VIEW task_statistics AS
SELECT 
    DATE(created_at) as date,
    task_type,
    status,
    COUNT(*) as count,
    AVG(cost_usd) as avg_cost,
    AVG(duration_seconds) as avg_duration,
    SUM(cost_usd) as total_cost
FROM agent_tasks
GROUP BY DATE(created_at), task_type, status
ORDER BY date DESC, task_type;

-- Comments
COMMENT ON TABLE agent_inbox IS 'Incoming messages and tasks';
COMMENT ON TABLE agent_tasks IS 'Processed tasks with state and results';
COMMENT ON COLUMN agent_inbox.priority IS '1 (highest) to 10 (lowest)';
COMMENT ON COLUMN agent_tasks.checkpoint_data IS 'State for resume after restart';
COMMENT ON COLUMN agent_tasks.cost_usd IS 'Cost in USD for this task';
