# Phase 9.9: Provider Capability Router

**Статус:** READY TO START (после emergency patch)  
**Приоритет:** CRITICAL  
**Зависимости:** Emergency patch должен быть применён

---

## 🎯 Цель

Создать умный router, который выбирает модель на основе capabilities, а не просто по списку fallback.

---

## 📋 Задача для Hermes

```
Start Phase 9.9: Provider Capability Router.

Prerequisites:
- Emergency patch applied and verified
- No HTTP 400 loop in logs
- hermes-gateway stable

Goal:
Build capability-aware model router that prevents incompatible fallback.

Components:
1. Model Capability Registry
2. Capability-Aware Router
3. Single Tool Mode
4. HTTP 400 Handler
5. Rate Limit Handler
6. Acceptance Tests
7. Documentation

Do not start Phase 10.0 until Phase 9.9 passes all acceptance tests.
```

---

## 1. Model Capability Registry

Создать файл: `/home/Bilirubin/.hermes/model_capabilities.json`

```json
{
  "models": {
    "anthropic/claude-sonnet-4": {
      "provider": "openrouter",
      "supports_tools": true,
      "supports_parallel_tool_calls": true,
      "max_context": 200000,
      "recommended_for": ["planning", "tool_use", "long_context"],
      "disabled_for": [],
      "cost_tier": "paid",
      "min_credits_required": 1.5
    },
    "anthropic/claude-3.5-sonnet": {
      "provider": "openrouter",
      "supports_tools": true,
      "supports_parallel_tool_calls": true,
      "max_context": 200000,
      "recommended_for": ["planning", "tool_use"],
      "disabled_for": [],
      "cost_tier": "paid",
      "min_credits_required": 0.5
    },
    "nvidia/nemotron-3-super-120b-a12b:free": {
      "provider": "openrouter",
      "supports_tools": true,
      "supports_parallel_tool_calls": true,
      "max_context": 32000,
      "recommended_for": ["tool_use", "fallback"],
      "disabled_for": [],
      "cost_tier": "free"
    },
    "google/gemma-4-26b-a4b-it:free": {
      "provider": "openrouter",
      "supports_tools": true,
      "supports_parallel_tool_calls": true,
      "max_context": 8000,
      "recommended_for": ["tool_use", "fallback"],
      "disabled_for": [],
      "cost_tier": "free"
    },
    "meta/llama-3.3-70b-instruct": {
      "provider": "nvidia",
      "supports_tools": true,
      "supports_parallel_tool_calls": false,
      "max_context": 128000,
      "recommended_for": ["summarization", "planning"],
      "disabled_for": ["tool_heavy", "multi_tool"],
      "cost_tier": "free",
      "single_tool_mode_required": true
    },
    "meta/llama-3.1-405b-instruct": {
      "provider": "nvidia",
      "supports_tools": true,
      "supports_parallel_tool_calls": false,
      "max_context": 128000,
      "recommended_for": ["planning"],
      "disabled_for": ["tool_heavy", "multi_tool"],
      "cost_tier": "free",
      "single_tool_mode_required": true
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
    },
    "summarization": {
      "requires": []
    }
  }
}
```

---

## 2. Capability-Aware Router

Создать файл: `/home/Bilirubin/.hermes/scripts/model_router.py`

```python
#!/usr/bin/env python3
"""
Capability-aware model router.
Selects model based on task requirements and model capabilities.
"""

import json
from pathlib import Path
from typing import Optional, Dict, List

CAPABILITIES_PATH = Path("/home/Bilirubin/.hermes/model_capabilities.json")


def load_capabilities() -> Dict:
    """Load model capabilities registry."""
    if not CAPABILITIES_PATH.exists():
        raise FileNotFoundError(f"Model capabilities not found: {CAPABILITIES_PATH}")
    return json.loads(CAPABILITIES_PATH.read_text())


def get_task_type(context: Dict) -> str:
    """
    Determine task type from context.
    
    Returns: tool_heavy | multi_tool | planning | summarization
    """
    # Check if task involves multiple tool calls
    if context.get("expected_tool_calls", 0) > 1:
        return "multi_tool"
    
    # Check if task is tool-heavy
    if context.get("requires_tools", False):
        return "tool_heavy"
    
    # Check if task is planning
    if "plan" in context.get("task_description", "").lower():
        return "planning"
    
    # Default
    return "summarization"


def is_model_compatible(model_name: str, task_type: str, capabilities: Dict) -> bool:
    """Check if model is compatible with task type."""
    model_caps = capabilities["models"].get(model_name)
    if not model_caps:
        return False
    
    # Check if model is disabled for this task type
    if task_type in model_caps.get("disabled_for", []):
        return False
    
    # Check task requirements
    task_reqs = capabilities["task_requirements"].get(task_type, {})
    required_caps = task_reqs.get("requires", [])
    
    for cap in required_caps:
        if not model_caps.get(cap, False):
            return False
    
    return True


def select_model(
    task_type: str,
    primary_model: str,
    fallback_models: List[str],
    primary_available: bool,
    openrouter_credits: Optional[float] = None
) -> Optional[str]:
    """
    Select best model for task.
    
    Returns:
        model_name if compatible model found
        None if no compatible model available (should checkpoint + pause)
    """
    capabilities = load_capabilities()
    
    # Try primary model first
    if primary_available:
        if is_model_compatible(primary_model, task_type, capabilities):
            # Check credits if needed
            primary_caps = capabilities["models"][primary_model]
            if primary_caps.get("cost_tier") == "paid":
                min_credits = primary_caps.get("min_credits_required", 0)
                if openrouter_credits is None or openrouter_credits >= min_credits:
                    return primary_model
    
    # Try fallback models
    for fallback in fallback_models:
        if is_model_compatible(fallback, task_type, capabilities):
            fallback_caps = capabilities["models"][fallback]
            
            # Check credits if needed
            if fallback_caps.get("cost_tier") == "paid":
                min_credits = fallback_caps.get("min_credits_required", 0)
                if openrouter_credits is None or openrouter_credits < min_credits:
                    continue
            
            return fallback
    
    # No compatible model found
    return None


def should_use_single_tool_mode(model_name: str) -> bool:
    """Check if model requires single tool mode."""
    capabilities = load_capabilities()
    model_caps = capabilities["models"].get(model_name, {})
    return model_caps.get("single_tool_mode_required", False)


if __name__ == "__main__":
    # Test
    caps = load_capabilities()
    print("Model Capabilities Registry loaded")
    print(f"Models: {len(caps['models'])}")
    print(f"Task types: {list(caps['task_requirements'].keys())}")
    
    # Test selection
    result = select_model(
        task_type="multi_tool",
        primary_model="anthropic/claude-sonnet-4",
        fallback_models=[
            "nvidia/nemotron-3-super-120b-a12b:free",
            "meta/llama-3.3-70b-instruct"
        ],
        primary_available=False,
        openrouter_credits=None
    )
    print(f"\nTest multi_tool task with primary unavailable:")
    print(f"Selected: {result}")
    print(f"Expected: nvidia/nemotron-3-super-120b-a12b:free (not llama)")
```

---

## 3. Single Tool Mode

Добавить в `/home/Bilirubin/.hermes/hermes-agent/` логику single tool mode:

```python
def enforce_single_tool_mode(prompt: str, model_name: str) -> str:
    """
    Add instruction for single tool mode if model requires it.
    """
    from model_router import should_use_single_tool_mode
    
    if should_use_single_tool_mode(model_name):
        return prompt + "\n\nIMPORTANT: Use at most ONE tool call per assistant message. Do not use parallel tool calls."
    
    return prompt
```

---

## 4. HTTP 400 Handler

Обновить error handler:

```python
def classify_api_error(error: Exception) -> str:
    """
    Classify API error.
    
    Returns:
        capability_mismatch | rate_limit | provider_failure | unknown
    """
    error_msg = str(error).lower()
    
    # Capability mismatch
    if "only supports single tool-calls" in error_msg:
        return "capability_mismatch"
    
    if "parallel tool" in error_msg:
        return "capability_mismatch"
    
    # Rate limit
    if "rate limit" in error_msg or "429" in error_msg:
        return "rate_limit"
    
    # Provider failure
    if "503" in error_msg or "502" in error_msg:
        return "provider_failure"
    
    return "unknown"


def handle_api_error(error: Exception, context: Dict) -> Dict:
    """
    Handle API error with appropriate action.
    
    Returns:
        {
            "action": "retry" | "fallback" | "checkpoint_and_pause" | "fail",
            "reason": str,
            "next_model": Optional[str]
        }
    """
    error_type = classify_api_error(error)
    
    if error_type == "capability_mismatch":
        # Do NOT retry same payload
        # Do NOT use same model
        # Try different model or pause
        return {
            "action": "checkpoint_and_pause",
            "reason": "Model capability mismatch - no compatible fallback",
            "next_model": None
        }
    
    if error_type == "rate_limit":
        # Try fallback if compatible
        from model_router import select_model
        task_type = context.get("task_type", "tool_heavy")
        next_model = select_model(
            task_type=task_type,
            primary_model=context["current_model"],
            fallback_models=context["fallback_models"],
            primary_available=False,
            openrouter_credits=context.get("openrouter_credits")
        )
        
        if next_model:
            return {
                "action": "fallback",
                "reason": "Primary rate limited, using compatible fallback",
                "next_model": next_model
            }
        else:
            return {
                "action": "checkpoint_and_pause",
                "reason": "Primary rate limited, no compatible fallback available",
                "next_model": None
            }
    
    # Other errors - retry with backoff
    return {
        "action": "retry",
        "reason": f"Transient error: {error_type}",
        "next_model": None
    }
```

---

## 5. Rate Limit Handler

```python
def handle_rate_limit(context: Dict) -> Dict:
    """
    Handle rate limit with cooldown and fallback.
    
    Returns:
        {
            "action": "cooldown" | "fallback" | "pause",
            "cooldown_seconds": int,
            "next_model": Optional[str]
        }
    """
    from model_router import select_model
    
    # Try compatible fallback
    task_type = context.get("task_type", "tool_heavy")
    next_model = select_model(
        task_type=task_type,
        primary_model=context["primary_model"],
        fallback_models=context["fallback_models"],
        primary_available=False,
        openrouter_credits=context.get("openrouter_credits")
    )
    
    if next_model:
        return {
            "action": "fallback",
            "cooldown_seconds": 0,
            "next_model": next_model
        }
    
    # No compatible fallback - pause and wait
    return {
        "action": "pause",
        "cooldown_seconds": 300,  # 5 minutes
        "next_model": None
    }
```

---

## 6. Acceptance Tests

Создать файл: `/home/Bilirubin/.hermes/tests/test_provider_router.py`

```python
#!/usr/bin/env python3
"""
Acceptance tests for Phase 9.9: Provider Capability Router
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from model_router import (
    load_capabilities,
    is_model_compatible,
    select_model,
    should_use_single_tool_mode
)


def test_capability_registry_loads():
    """Test 1: Capability registry loads successfully."""
    caps = load_capabilities()
    assert "models" in caps
    assert "task_requirements" in caps
    assert len(caps["models"]) > 0
    print("✅ Test 1: Capability registry loads")


def test_llama_incompatible_with_multi_tool():
    """Test 2: NVIDIA llama is incompatible with multi_tool tasks."""
    caps = load_capabilities()
    compatible = is_model_compatible(
        "meta/llama-3.3-70b-instruct",
        "multi_tool",
        caps
    )
    assert not compatible, "llama should NOT be compatible with multi_tool"
    print("✅ Test 2: llama incompatible with multi_tool")


def test_nemotron_compatible_with_multi_tool():
    """Test 3: Nemotron is compatible with multi_tool tasks."""
    caps = load_capabilities()
    compatible = is_model_compatible(
        "nvidia/nemotron-3-super-120b-a12b:free",
        "multi_tool",
        caps
    )
    assert compatible, "nemotron should be compatible with multi_tool"
    print("✅ Test 3: nemotron compatible with multi_tool")


def test_fallback_selection_skips_incompatible():
    """Test 4: Fallback selection skips incompatible models."""
    result = select_model(
        task_type="multi_tool",
        primary_model="anthropic/claude-sonnet-4",
        fallback_models=[
            "meta/llama-3.3-70b-instruct",  # incompatible
            "nvidia/nemotron-3-super-120b-a12b:free"  # compatible
        ],
        primary_available=False,
        openrouter_credits=None
    )
    assert result == "nvidia/nemotron-3-super-120b-a12b:free"
    print("✅ Test 4: Fallback skips incompatible llama")


def test_no_compatible_fallback_returns_none():
    """Test 5: Returns None when no compatible fallback exists."""
    result = select_model(
        task_type="multi_tool",
        primary_model="anthropic/claude-sonnet-4",
        fallback_models=[
            "meta/llama-3.3-70b-instruct",  # incompatible
            "meta/llama-3.1-405b-instruct"  # also incompatible
        ],
        primary_available=False,
        openrouter_credits=None
    )
    assert result is None, "Should return None when no compatible fallback"
    print("✅ Test 5: Returns None for no compatible fallback")


def test_single_tool_mode_detection():
    """Test 6: Detects models requiring single tool mode."""
    assert should_use_single_tool_mode("meta/llama-3.3-70b-instruct")
    assert not should_use_single_tool_mode("nvidia/nemotron-3-super-120b-a12b:free")
    print("✅ Test 6: Single tool mode detection works")


def test_primary_model_preferred():
    """Test 7: Primary model is preferred when available."""
    result = select_model(
        task_type="multi_tool",
        primary_model="anthropic/claude-sonnet-4",
        fallback_models=["nvidia/nemotron-3-super-120b-a12b:free"],
        primary_available=True,
        openrouter_credits=5.0
    )
    assert result == "anthropic/claude-sonnet-4"
    print("✅ Test 7: Primary model preferred when available")


def test_credits_check():
    """Test 8: Credits check prevents expensive model when low."""
    result = select_model(
        task_type="multi_tool",
        primary_model="anthropic/claude-sonnet-4",
        fallback_models=["nvidia/nemotron-3-super-120b-a12b:free"],
        primary_available=True,
        openrouter_credits=0.1  # Too low
    )
    assert result == "nvidia/nemotron-3-super-120b-a12b:free"
    print("✅ Test 8: Credits check works")


if __name__ == "__main__":
    print("Running Phase 9.9 Acceptance Tests\n")
    
    try:
        test_capability_registry_loads()
        test_llama_incompatible_with_multi_tool()
        test_nemotron_compatible_with_multi_tool()
        test_fallback_selection_skips_incompatible()
        test_no_compatible_fallback_returns_none()
        test_single_tool_mode_detection()
        test_primary_model_preferred()
        test_credits_check()
        
        print("\n✅ All tests passed!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
```

---

## 7. Integration

Обновить основной agent код для использования router:

```python
# В начале agent loop
from model_router import select_model, should_use_single_tool_mode
from error_handler import handle_api_error

# Определить task type
task_type = determine_task_type(context)

# Выбрать модель
selected_model = select_model(
    task_type=task_type,
    primary_model=config["primary_model"],
    fallback_models=config["fallback_models"],
    primary_available=is_primary_available(),
    openrouter_credits=get_openrouter_credits()
)

if selected_model is None:
    # No compatible model - checkpoint and pause
    save_checkpoint(context)
    notify_user("Task paused: no compatible model available")
    return

# Enforce single tool mode if needed
if should_use_single_tool_mode(selected_model):
    prompt = enforce_single_tool_mode(prompt, selected_model)

# Make API call
try:
    response = call_model(selected_model, prompt)
except Exception as error:
    action = handle_api_error(error, context)
    
    if action["action"] == "checkpoint_and_pause":
        save_checkpoint(context)
        notify_user(f"Task paused: {action['reason']}")
        return
    
    # ... handle other actions
```

---

## 8. Verification Commands

```bash
# 1. Run acceptance tests
/home/Bilirubin/.hermes/venv/bin/python3 \
  /home/Bilirubin/.hermes/tests/test_provider_router.py

# 2. Verify model router works
/home/Bilirubin/.hermes/venv/bin/python3 \
  /home/Bilirubin/.hermes/scripts/model_router.py

# 3. Check no HTTP 400 in logs
sudo journalctl -u hermes-gateway --since "1 hour ago" | \
  grep -i "single tool-calls\|HTTP 400"

# 4. Restart service
sudo systemctl restart hermes-gateway

# 5. Check service status
systemctl status hermes-gateway
```

---

## ✅ Phase 9.9 Complete Criteria

- ✅ Model capability registry created
- ✅ Capability-aware router implemented
- ✅ Single tool mode enforced for incompatible models
- ✅ HTTP 400 handler prevents retry loop
- ✅ Rate limit handler uses compatible fallback or pauses
- ✅ All acceptance tests pass
- ✅ No HTTP 400 loop in logs
- ✅ hermes-gateway stable
- ✅ Documentation complete

---

## 📊 Status Label

After completion: `provider_router_complete`

NOT: `production_ready` (that comes after Phase 10.0)

---

## 🔜 Next Step

After Phase 9.9 passes all tests:

**Phase 10.0: Reliable Agent Runtime**
- Persistent inbox queue
- Task orchestrator
- Checkpoint + auto resume
- MCP auto-reconnect
- Interruption policy

---

**READY TO START** (после emergency patch)
