#!/usr/bin/env python3
"""
Unified configuration loader for Hermes.
Loads repository config first, then falls back to ~/.hermes/config.yaml.

Phase 1, Day 3: Config Consolidation
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


CONFIG_PATH_ENV_VARS = ("HERMES_CONFIG_PATH", "HERMES_APP_CONFIG")


def resolve_default_config_path() -> Path:
    """Resolve the default config path for app and runtime contexts."""
    for env_var in CONFIG_PATH_ENV_VARS:
        env_path = os.getenv(env_var)
        if env_path:
            return Path(env_path).expanduser()

    cwd = Path.cwd()
    module_root = Path(__file__).resolve().parent.parent
    candidates = [
        cwd / "config/config.yaml",
        cwd / "config/config.yaml.template",
        module_root / "config/config.yaml",
        module_root / "config/config.yaml.template",
        Path.home() / ".hermes/config.yaml",
    ]

    for path in candidates:
        if path.exists():
            return path

    return candidates[-1]


class ConfigLoader:
    """Load and manage Hermes configuration."""
    
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = resolve_default_config_path()
        
        self.config_path = Path(config_path).expanduser()
        self._config = None
        self._env_vars_used = set()
        self._env_snapshot = {}
    
    def load(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")
        
        with open(self.config_path) as f:
            raw_config = yaml.safe_load(f) or {}
        
        # Substitute environment variables
        self._env_vars_used = set()
        self._config = self._substitute_env_vars(raw_config)
        self._env_snapshot = {
            var_name: os.getenv(var_name) for var_name in self._env_vars_used
        }
        
        return self._config
    
    def _substitute_env_vars(self, config: Any) -> Any:
        """Recursively substitute ${VAR} with environment variables."""
        if isinstance(config, dict):
            return {k: self._substitute_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._substitute_env_vars(item) for item in config]
        elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
            var_name = config[2:-1]
            self._env_vars_used.add(var_name)
            value = os.getenv(var_name)
            if value is None:
                raise ValueError(f"Environment variable not set: {var_name}")
            return value
        else:
            return config

    def uses_current_environment(self) -> bool:
        """Return whether the loaded config still matches current env values."""
        return all(
            os.getenv(var_name) == self._env_snapshot.get(var_name)
            for var_name in self._env_vars_used
        )
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """Get config value by dot-separated path."""
        if self._config is None:
            self.load()
        
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def validate(self) -> bool:
        """Validate configuration."""
        if self._config is None:
            self.load()
        
        # Check required sections
        required_sections = ['hermes', 'database', 'providers', 'models']
        for section in required_sections:
            if section not in self._config:
                raise ValueError(f"Missing required section: {section}")
        
        # Check required database fields
        db_fields = ['host', 'port', 'name', 'user', 'password']
        for field in db_fields:
            if field not in self._config['database']:
                raise ValueError(f"Missing database field: {field}")
        
        # Check required provider fields
        for provider_name, provider_config in self._config['providers'].items():
            if 'api_key' not in provider_config:
                raise ValueError(f"Missing api_key for provider: {provider_name}")
        
        return True


# Global config instance
_config = None


def get_config(reload: bool = False) -> ConfigLoader:
    """Get global config instance."""
    global _config
    config_path = resolve_default_config_path()
    if (
        reload
        or _config is None
        or _config.config_path != config_path
        or not _config.uses_current_environment()
    ):
        _config = ConfigLoader(config_path)
        _config.load()
    return _config


if __name__ == "__main__":
    # Test config loading
    config = ConfigLoader()
    config.load()
    config.validate()
    
    print("Config loaded successfully")
    print(f"Hermes home: {config.get('hermes.home')}")
    print(f"Database: {config.get('database.name')}")
    print(f"Primary model: {config.get('models.primary.model')}")
