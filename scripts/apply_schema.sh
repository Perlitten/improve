#!/bin/bash
# Apply database schema for task queue
# Phase 1, Day 2

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_DIR="$SCRIPT_DIR/../sql"
ENV_FILE="$HOME/.hermes/automation.env"

# Load environment
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
else
    echo "Error: $ENV_FILE not found"
    exit 1
fi

# Apply schema
echo "Applying task queue schema..."
PGPASSWORD="$POSTGRES_PASSWORD" psql \
    -h 127.0.0.1 \
    -p 5432 \
    -U "$POSTGRES_USER" \
    -d rag \
    -f "$SQL_DIR/001_create_task_queue.sql"

echo "✅ Schema applied successfully"

# Verify tables created
echo ""
echo "Verifying tables..."
PGPASSWORD="$POSTGRES_PASSWORD" psql \
    -h 127.0.0.1 \
    -p 5432 \
    -U "$POSTGRES_USER" \
    -d rag \
    -c "\dt agent_*"

echo ""
echo "✅ Task queue ready"
