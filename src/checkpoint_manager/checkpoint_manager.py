"""
Checkpoint Manager for Phase 10.0

Manages atomic, secure checkpoint storage tied to the task workspace.

Functions:
- save_checkpoint(data: dict) -> str: Saves checkpoint with timestamped filename, validates JSON, redacts secrets.
- load_latest_checkpoint() -> dict or None: Loads most recent checkpoint.
- list_checkpoints() -> list[str]: Returns sorted list of checkpoint filenames.
- _redact_secrets(data: dict) -> dict: Recursively removes keys matching secret patterns.
- _is_secret_key(key: str) -> bool: Detects common secret key patterns.
- _is_secret_value(value: Any) -> bool: Detects secret-like string values.

All writes use atomic temp-file replacement to prevent corruption.
"""

import os
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Exact secret key matches (case-insensitive)
SECRET_KEY_EXACT = {
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "passwd",
    "authorization",
    "bearer",
    "secret",
    "client_secret",
    "secret_key",
}

# Secret key suffixes (case-insensitive)
SECRET_KEY_SUFFIXES = (
    "_api_key",
    "_token",
    "_access_token",
    "_refresh_token",
    "_password",
    "_passwd",
    "_client_secret",
    "_secret_key",
)

# Checkpoint directory name (relative to workspace)
CHECKPOINT_DIR = "checkpoints"


def _get_checkpoint_dir() -> Path:
    """Return the checkpoint directory path.
    If CHECKPOINT_DIR is absolute, use it directly.
    Otherwise, resolve relative to HERMES_WORKSPACE environment variable.
    """
    checkpoint_dir = Path(CHECKPOINT_DIR)
    if checkpoint_dir.is_absolute():
        return checkpoint_dir
    workspace = Path(os.environ.get("HERMES_WORKSPACE", "/home/Bilirubin/workspace"))
    return workspace / "hermes" / "src" / "checkpoint_manager" / checkpoint_dir


def _is_secret_key(key: str) -> bool:
    """Check if key is an exact secret match or has a secret suffix.
    Normalizes key: lower, strip, replace "-" with "_".
    """
    key_text = str(key).strip().lower().replace("-", "_")
    if key_text in SECRET_KEY_EXACT:
        return True
    return any(key_text.endswith(suffix) for suffix in SECRET_KEY_SUFFIXES)


def _is_secret_value(value: Any) -> bool:
    """Check if string value matches secret-like pattern."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    lower = text.lower()
    return (
        text.startswith("sk-") or
        text.startswith("sk-or-v1-") or
        lower.startswith("bearer ")
    )


def _redact_secrets(data: Any) -> Any:
    """Recursively redact secret keys and values from nested dict/list structures."""
    if isinstance(data, dict):
        result = {}
        for key, item in data.items():
            if _is_secret_key(key):
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact_secrets(item)
        return result
    elif isinstance(data, list):
        return [_redact_secrets(item) for item in data]
    else:
        if _is_secret_value(data):
            return "[REDACTED]"
        else:
            return data


def save_checkpoint(data: Dict[str, Any]) -> str:
    """Save a checkpoint with a timestamped filename in the checkpoints directory.
    Redacts secrets before saving. Returns the full path to the saved file.
    """
    checkpoint_path = _get_checkpoint_dir()
    checkpoint_path.mkdir(parents=True, exist_ok=True)
    
    # Redact secrets
    cleaned_data = _redact_secrets(data)
    
    # Include nanoseconds so fast successive checkpoints do not overwrite.
    timestamp = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{time.time_ns()}"
    filename = f"checkpoint_{timestamp}.json"
    filepath = checkpoint_path / filename
    
    # Atomic write: write to temp file, then rename
    temp_filepath = filepath.with_suffix(".tmp")
    try:
        with open(temp_filepath, "w", encoding="utf-8") as f:
            json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
        temp_filepath.rename(filepath)
        return str(filepath)
    except TypeError as e: # Catch only JSON serialization errors
        # Clean up temp file if exists
        if temp_filepath.exists():
            temp_filepath.unlink()
        raise # Re-raise TypeError unchanged
    except Exception as e:
        # Clean up temp file if exists
        if temp_filepath.exists():
            temp_filepath.unlink()
        raise RuntimeError(f"Failed to save checkpoint: {e}")


def load_latest_checkpoint() -> Optional[Dict[str, Any]]:
    """Load the most recent checkpoint file. Returns None if no checkpoints exist."""
    checkpoint_path = _get_checkpoint_dir()
    if not checkpoint_path.exists() or not checkpoint_path.is_dir():
        return None
    
    checkpoint_files = [
        f for f in checkpoint_path.iterdir()
        if f.name.startswith("checkpoint_") and f.suffix == ".json" and f.is_file()
    ]
    
    if not checkpoint_files:
        return None
    
    # Sort by timestamp (descending)
    checkpoint_files.sort(key=lambda x: x.name.replace("checkpoint_", "").replace(".json", ""), reverse=True)
    latest_file = checkpoint_files[0]
    
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to load checkpoint {latest_file}: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to load checkpoint {latest_file}: {e}")


def list_checkpoints() -> List[str]:
    """Return a sorted list of checkpoint filenames (oldest first).
    Only returns up to 3 valid, non-corrupt checkpoint files from the configured workspace directory.
    """
    checkpoint_path = _get_checkpoint_dir()
    if not checkpoint_path.exists() or not checkpoint_path.is_dir():
        return []

    checkpoint_files = []
    for f in checkpoint_path.iterdir():
        if not (f.name.startswith("checkpoint_") and f.suffix == ".json" and f.is_file()):
            continue
        # Skip if file is not readable or not valid JSON
        try:
            with open(f, "r", encoding="utf-8") as fp:
                json.load(fp)
            checkpoint_files.append(f.name)
        except (json.JSONDecodeError, OSError):
            continue

    # Sort by timestamp (descending)
    checkpoint_files.sort(key=lambda x: x.replace("checkpoint_", "").replace(".json", ""), reverse=True)
    # Take only the 3 most recent
    checkpoint_files = checkpoint_files[:3]

    # Return sorted oldest first
    return sorted(checkpoint_files)

# --- Unit test stub ---
# See test_checkpoint_manager.py for full test suite.
