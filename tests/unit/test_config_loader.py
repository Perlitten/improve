"""Unit tests for config_loader.py"""

import pytest
import os
import tempfile
from pathlib import Path
import sys

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from config_loader import ConfigLoader


@pytest.fixture
def sample_config():
    """Sample config for testing"""
    return """
hermes:
  home: /test/.hermes
  log_level: DEBUG

database:
  host: localhost
  port: 5432
  name: test_db
  user: ${TEST_USER}
  password: ${TEST_PASSWORD}

providers:
  openrouter:
    api_key: ${OPENROUTER_KEY}

models:
  primary:
    model: test-model
    max_cost_per_task: 1.00
"""


@pytest.fixture
def config_file(sample_config, monkeypatch):
    """Create temporary config file"""
    # Set environment variables
    monkeypatch.setenv("TEST_USER", "test_user")
    monkeypatch.setenv("TEST_PASSWORD", "test_pass")
    monkeypatch.setenv("OPENROUTER_KEY", "test_key")
    
    # Create temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(sample_config)
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    temp_path.unlink()


@pytest.mark.unit
class TestConfigLoader:
    """Test config loader functionality"""
    
    def test_load_config(self, config_file):
        """Test loading config from file"""
        loader = ConfigLoader(config_file)
        config = loader.load()
        
        assert config is not None
        assert 'hermes' in config
        assert 'database' in config
    
    def test_env_var_substitution(self, config_file):
        """Test environment variable substitution"""
        loader = ConfigLoader(config_file)
        loader.load()
        
        assert loader.get('database.user') == 'test_user'
        assert loader.get('database.password') == 'test_pass'
        assert loader.get('providers.openrouter.api_key') == 'test_key'
    
    def test_get_nested_value(self, config_file):
        """Test getting nested config values"""
        loader = ConfigLoader(config_file)
        loader.load()
        
        assert loader.get('hermes.home') == '/test/.hermes'
        assert loader.get('hermes.log_level') == 'DEBUG'
        assert loader.get('database.port') == 5432
    
    def test_get_with_default(self, config_file):
        """Test getting value with default"""
        loader = ConfigLoader(config_file)
        loader.load()
        
        assert loader.get('nonexistent.key', 'default') == 'default'
    
    def test_validate_success(self, config_file):
        """Test validation with valid config"""
        loader = ConfigLoader(config_file)
        loader.load()
        
        assert loader.validate() == True
    
    def test_validate_missing_section(self, config_file):
        """Test validation with missing section"""
        loader = ConfigLoader(config_file)
        loader.load()
        
        # Remove required section
        del loader._config['models']
        
        with pytest.raises(ValueError, match="Missing required section: models"):
            loader.validate()
    
    def test_validate_missing_database_field(self, config_file):
        """Test validation with missing database field"""
        loader = ConfigLoader(config_file)
        loader.load()
        
        # Remove required field
        del loader._config['database']['user']
        
        with pytest.raises(ValueError, match="Missing database field: user"):
            loader.validate()
    
    def test_validate_missing_provider_api_key(self, config_file):
        """Test validation with missing provider api_key"""
        loader = ConfigLoader(config_file)
        loader.load()
        
        # Remove api_key
        del loader._config['providers']['openrouter']['api_key']
        
        with pytest.raises(ValueError, match="Missing api_key for provider: openrouter"):
            loader.validate()
    
    def test_missing_env_var(self, config_file, monkeypatch):
        """Test error when environment variable missing"""
        # Unset environment variable
        monkeypatch.delenv("TEST_USER", raising=False)
        
        loader = ConfigLoader(config_file)
        
        with pytest.raises(ValueError, match="Environment variable not set: TEST_USER"):
            loader.load()
    
    def test_file_not_found(self):
        """Test error when config file not found"""
        loader = ConfigLoader(Path("/nonexistent/config.yaml"))
        
        with pytest.raises(FileNotFoundError):
            loader.load()
    
    def test_nested_env_vars(self, monkeypatch):
        """Test environment variables in nested structures"""
        monkeypatch.setenv("TEST_VAR", "test_value")
        
        config_content = """
nested:
  level1:
    level2: ${TEST_VAR}
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            temp_path = Path(f.name)
        
        try:
            loader = ConfigLoader(temp_path)
            loader.load()
            
            assert loader.get('nested.level1.level2') == 'test_value'
        finally:
            temp_path.unlink()
    
    def test_list_with_env_vars(self, monkeypatch):
        """Test environment variables in lists"""
        monkeypatch.setenv("MODEL_1", "model-1")
        monkeypatch.setenv("MODEL_2", "model-2")
        
        config_content = """
models:
  - ${MODEL_1}
  - ${MODEL_2}
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            temp_path = Path(f.name)
        
        try:
            loader = ConfigLoader(temp_path)
            loader.load()
            
            assert loader.get('models')[0] == 'model-1'
            assert loader.get('models')[1] == 'model-2'
        finally:
            temp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
