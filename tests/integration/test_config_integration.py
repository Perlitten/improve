"""Integration tests for config with other components"""

import pytest
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from config_loader import ConfigLoader, get_config


def set_required_config_env(monkeypatch, **overrides):
    """Set env vars needed by config/config.yaml.template."""
    values = {
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test_pass",
        "OPENROUTER_API_KEY": "test_key",
        "NVIDIA_API_KEY": "test_key",
    }
    values.update(overrides)

    for key, value in values.items():
        monkeypatch.setenv(key, value)


@pytest.mark.integration
class TestConfigIntegration:
    """Test config integration with other components"""
    
    def test_config_with_task_orchestrator(self, monkeypatch):
        """Test config works with TaskOrchestrator"""
        set_required_config_env(monkeypatch)
        
        # This would test actual integration
        # For now, just verify config can be loaded
        config = get_config()
        
        assert config.get('database.user') is not None
        assert config.get('database.password') is not None
    
    def test_config_with_model_router(self, monkeypatch):
        """Test config works with model router"""
        set_required_config_env(monkeypatch)
        
        config = get_config()
        
        # Verify model config
        primary_model = config.get('models.primary.model')
        assert primary_model is not None
        
        # Verify provider config
        openrouter_key = config.get('providers.openrouter.api_key')
        assert openrouter_key == 'test_key'
    
    def test_config_provides_all_required_settings(self, monkeypatch):
        """Test config provides all settings needed by components"""
        set_required_config_env(
            monkeypatch,
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
        )
        
        config = get_config()
        
        # Database settings
        assert config.get('database.host') is not None
        assert config.get('database.port') is not None
        assert config.get('database.name') is not None
        
        # Provider settings
        assert config.get('providers.openrouter.api_key') is not None
        assert config.get('providers.openrouter.base_url') is not None
        
        # Model settings
        assert config.get('models.primary.model') is not None
        assert config.get('models.fallback') is not None
        
        # Task queue settings
        assert config.get('task_queue.max_concurrent') is not None
        assert config.get('task_queue.checkpoint_interval') is not None
        
        # Cost tracking settings
        assert config.get('cost_tracking.enabled') is not None
        assert config.get('cost_tracking.daily_budget') is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
