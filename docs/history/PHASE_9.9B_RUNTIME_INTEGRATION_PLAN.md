# Phase 9.9b: Provider Router Runtime Integration Plan

## Current State Analysis

### Where Fallback Happens
**File:** `/home/Bilirubin/.hermes/hermes-agent/run_agent.py`  
**Function:** `_try_activate_fallback()` (lines 7434-7628)  
**Current Logic:**
```python
fb = self._fallback_chain[self._fallback_index]
self._fallback_index += 1
fb_provider = (fb.get("provider") or "").strip().lower()
fb_model = (fb.get("model") or "").strip()
if not fb_provider or not fb_model:
    return self._try_activate_fallback()  # skip invalid, try next
```

**Problem:** No capability check — blindly tries next fallback even if incompatible (e.g., llama-3.3 for tool-heavy tasks).

### Integration Point
Need to insert capability check **before** line 7458 (`fb = self._fallback_chain[...]`):

```python
# NEW: Check model capabilities before activating fallback
from .provider_capability_check import is_model_compatible_for_task

task_type = "tool_heavy" if self._has_active_tool_calls() else "simple"
if not is_model_compatible_for_task(fb_model, fb_provider, task_type):
    logging.warning(
        "Skipping incompatible fallback: %s via %s (task_type=%s)",
        fb_model, fb_provider, task_type
    )
    return self._try_activate_fallback()  # try next in chain
```

## Required Changes

### 1. Create Capability Check Module
**File:** `/home/Bilirubin/.hermes/hermes-agent/provider_capability_check.py`

```python
#!/usr/bin/env python3
"""
Provider Capability Check — Runtime integration for model fallback.
Checks if a model is compatible with the current task requirements.
"""

import json
import logging
from pathlib import Path

CAPABILITIES_FILE = Path("/home/Bilirubin/.hermes/model_capabilities.json")

def load_capabilities_registry():
    """Load model capabilities registry."""
    if not CAPABILITIES_FILE.exists():
        logging.warning("Capabilities file not found: %s", CAPABILITIES_FILE)
        return {}
    try:
        with open(CAPABILITIES_FILE, 'r') as f:
            return json.load(f).get('registry', {})
    except Exception as e:
        logging.error("Failed to load capabilities: %s", e)
        return {}

def is_model_compatible_for_task(model_name: str, provider: str, task_type: str = "tool_heavy") -> bool:
    """
    Check if model is compatible with task requirements.
    
    Args:
        model_name: Full model name (e.g., "meta/llama-3.3-70b-instruct")
        provider: Provider name (e.g., "nvidia")
        task_type: "tool_heavy" or "simple"
    
    Returns:
        True if compatible, False if incompatible
    """
    registry = load_capabilities_registry()
    
    # Normalize model name (handle "provider/model" format)
    if '/' in model_name:
        model_key = model_name
    else:
        model_key = f"{provider}/{model_name}" if provider else model_name
    
    # Try exact match first
    if model_key in registry:
        caps = registry[model_key]
    else:
        # Try partial match (last part of model name)
        model_short = model_name.split('/')[-1] if '/' in model_name else model_name
        found = False
        for key in registry:
            if key.endswith(model_short) or model_short in key:
                caps = registry[key]
                found = True
                break
        if not found:
            # Unknown model — assume compatible (fail open)
            logging.warning("Unknown model in registry, assuming compatible: %s", model_name)
            return True
    
    # Check disabled_for
    disabled_for = caps.get('disabled_for', [])
    if task_type in disabled_for:
        logging.info(
            "Model %s disabled for %s tasks (disabled_for: %s)",
            model_name, task_type, disabled_for
        )
        return False
    
    # Check single_tool_only for tool_heavy tasks
    if task_type == "tool_heavy" and caps.get('single_tool_only', False):
        logging.info(
            "Model %s supports only single tool calls, incompatible with %s tasks",
            model_name, task_type
        )
        return False
    
    if task_type == "tool_heavy" and not caps.get('supports_parallel_tool_calls', False):
        logging.info(
            "Model %s does not support parallel tool calls, incompatible with %s tasks",
            model_name, task_type
        )
        return False
    
    return True

def get_compatible_fallback_from_chain(fallback_chain: list, task_type: str = "tool_heavy") -> dict:
    """
    Find first compatible fallback from chain.
    
    Args:
        fallback_chain: List of fallback dicts with 'model' and 'provider' keys
        task_type: "tool_heavy" or "simple"
    
    Returns:
        First compatible fallback dict, or None if no compatible fallback
    """
    for fb in fallback_chain:
        model = fb.get('model', '')
        provider = fb.get('provider', '')
        if is_model_compatible_for_task(model, provider, task_type):
            return fb
    return None
```

### 2. Patch run_agent.py

**Location:** Line ~7458 in `_try_activate_fallback()`

**Before:**
```python
fb = self._fallback_chain[self._fallback_index]
self._fallback_index += 1
fb_provider = (fb.get("provider") or "").strip().lower()
fb_model = (fb.get("model") or "").strip()
if not fb_provider or not fb_model:
    return self._try_activate_fallback()  # skip invalid, try next
```

**After:**
```python
fb = self._fallback_chain[self._fallback_index]
self._fallback_index += 1
fb_provider = (fb.get("provider") or "").strip().lower()
fb_model = (fb.get("model") or "").strip()
if not fb_provider or not fb_model:
    return self._try_activate_fallback()  # skip invalid, try next

# NEW: Capability check for tool-heavy tasks
from .provider_capability_check import is_model_compatible_for_task
task_type = "tool_heavy" if getattr(self, '_has_pending_tool_calls', False) else "simple"
if not is_model_compatible_for_task(fb_model, fb_provider, task_type):
    logging.warning(
        "Skipping incompatible fallback: %s via %s (task_type=%s, blocked by capability check)",
        fb_model, fb_provider, task_type
    )
    return self._try_activate_fallback()  # try next in chain
```

### 3. Update Config Fallback Chain
Already done in Phase 9.9 hotfix:
```yaml
fallback_model:
  model: "qwen/qwen3.5-397b-a17b"
  provider: nvidia
  fallback_chain:
    - "kr/claude-sonnet-4.5"
    - "qwen/qwen3.5-397b-a17b"
    - "moonshotai/kimi-k2.6"
  blocked_for_tool_tasks:
    - "meta/llama-3.3-70b-instruct"
    - "deepseek-ai/deepseek-coder-6.7b-instruct"
```

## Acceptance Tests

### Test 1: Capability Check Module
```bash
cd ~/.hermes/hermes-agent
python3 -c "from provider_capability_check import is_model_compatible_for_task; print(is_model_compatible_for_task('meta/llama-3.3-70b-instruct', 'nvidia', 'tool_heavy'))"
# Expected: False
```

### Test 2: Runtime Integration
```bash
# Simulate fallback activation with tool-heavy task
python3 -c "
from provider_capability_check import get_compatible_fallback_from_chain
chain = [
    {'model': 'meta/llama-3.3-70b-instruct', 'provider': 'nvidia'},
    {'model': 'qwen/qwen3.5-397b-a17b', 'provider': 'nvidia'},
]
result = get_compatible_fallback_from_chain(chain, 'tool_heavy')
print(result)
# Expected: {'model': 'qwen/qwen3.5-397b-a17b', 'provider': 'nvidia'}
"
```

### Test 3: Full Agent Test (when providers stable)
1. Start agent with tool-heavy task
2. Simulate primary rate limit
3. Verify fallback skips llama-3.3
4. Verify fallback selects qwen3.5 or claude-sonnet-4.5

## Rollback Plan
If integration causes issues:
1. Remove import from run_agent.py
2. Delete provider_capability_check.py
3. Restore config.yaml from backup

## Status
- [ ] Capability check module created
- [ ] run_agent.py patched
- [ ] Unit tests pass
- [ ] Integration test passes
- [ ] Safe mode can be disabled

---
**Next:** Create provider_status.md and continue with Phase 9.9b verification.
