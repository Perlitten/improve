"""Pytest configuration and shared fixtures"""

import pytest
import os
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def test_config():
    """Test configuration"""
    return {
        "test_mode": True,
        "db_name": "rag_test",
        "log_level": "DEBUG"
    }


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables"""
    test_env = {
        "HERMES_HOME": "/tmp/hermes_test",
        "OPENROUTER_API_KEY": "test-key-openrouter",
        "NVIDIA_API_KEY": "test-key-nvidia",
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test_pass"
    }
    
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)
    
    return test_env


@pytest.fixture
def sample_capabilities():
    """Sample model capabilities for testing"""
    return {
        "registry": {
            "anthropic/claude-sonnet-4": {
                "provider": "openrouter",
                "supports_tools": True,
                "supports_parallel_tool_calls": True,
                "max_context": 200000,
                "cost_tier": "paid",
                "min_credits_required": 1.5
            },
            "nvidia/nemotron-3-super-120b-a12b:free": {
                "provider": "openrouter",
                "supports_tools": True,
                "supports_parallel_tool_calls": False,
                "max_context": 32000,
                "cost_tier": "free",
                "single_tool_mode_required": True,
                "disabled_for": ["tool_heavy", "multi_tool"]
            },
            "deepseek/deepseek-v4-flash": {
                "provider": "openrouter",
                "supports_tools": True,
                "supports_parallel_tool_calls": True,
                "max_context": 64000,
                "cost_tier": "cheap_paid"
            },
            "qwen/qwen3-next-80b-a3b-instruct": {
                "provider": "nvidia",
                "supports_tools": True,
                "supports_parallel_tool_calls": True,
                "max_context": 128000,
                "cost_tier": "free"
            },
            "google/gemma-4-26b-a4b-it:free": {
                "provider": "openrouter",
                "enabled": False,
                "selectable": False,
                "live_probe_status": "rate_limited_429_upstream_2026-05-06",
                "supports_tools": False,
                "supports_parallel_tool_calls": False,
                "disabled_for": ["all"],
                "cost_tier": "free"
            },
            "meta/llama-3.3-70b-instruct": {
                "provider": "nvidia",
                "supports_tools": True,
                "supports_parallel_tool_calls": False,
                "max_context": 128000,
                "cost_tier": "free",
                "single_tool_mode_required": True
            }
        },
        "task_requirements": {
            "tool_heavy": {
                "requires": ["supports_tools", "supports_parallel_tool_calls"]
            },
            "multi_tool": {
                "requires": ["supports_parallel_tool_calls"]
            },
            "planning": {
                "requires": []
            }
        }
    }


@pytest.fixture
def db_connection():
    """Database connection for testing"""
    import psycopg2
    from pathlib import Path
    
    # Read env
    env_path = Path.home() / ".hermes/automation.env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env[key.strip()] = value.strip()
    
    # Connect to test database. Local developer machines may not have the
    # cloud Postgres tunnel or automation credentials configured.
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB", "rag"),
            user=os.getenv("POSTGRES_USER", env.get("POSTGRES_USER", "automation")),
            password=os.getenv("POSTGRES_PASSWORD", env.get("POSTGRES_PASSWORD", "")),
        )
    except psycopg2.OperationalError as exc:
        if os.getenv("HERMES_TEST_REQUIRE_DB") == "1":
            raise
        pytest.skip(f"Postgres test database unavailable: {exc}")
    
    yield conn
    
    # Cleanup: rollback any changes
    conn.rollback()
    conn.close()


@pytest.fixture
def orchestrator(db_connection):
    """TaskOrchestrator instance for testing (V2 - UUID schema)"""
    from task_orchestrator_v2 import TaskOrchestrator
    
    # Clean up test data before each test
    with db_connection.cursor() as cur:
        # Delete tasks created by test inbox entries
        cur.execute("""
            DELETE FROM agent_tasks 
            WHERE id IN (
                SELECT active_task_id FROM agent_inbox WHERE source = 'test'
            )
        """)
        # Delete test inbox entries
        cur.execute("DELETE FROM agent_inbox WHERE source = 'test'")
        db_connection.commit()
    
    return TaskOrchestrator()
