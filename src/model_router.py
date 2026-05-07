#!/usr/bin/env python3
"""
Capability-aware model router.
Selects model based on task requirements and model capabilities.
"""

import json
from pathlib import Path
from typing import Optional, Dict, List

CAPABILITIES_PATH = Path("/home/Bilirubin/.hermes/model_capabilities.json")
BAD_LIVE_STATUS_MARKERS = (
    "failed",
    "rate_limited",
    "disabled",
    "eol",
    "not_listed",
)


def load_capabilities_full() -> Dict:
    """Load full model capabilities file."""
    paths_to_check = [
        Path.home() / ".hermes/model_capabilities.json",
        CAPABILITIES_PATH,
        Path(__file__).parent.parent / "config/model_capabilities.json",
        Path(__file__).parent.parent / "maintenance/model_capabilities.json",
        Path(__file__).parent / "model_capabilities.json",
    ]
    for path in paths_to_check:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
    return {"registry": {}, "task_requirements": {}}


def resolve_model_caps(model_name: str, registry: Dict) -> Optional[Dict]:
    """Resolve model capabilities using exact match first, then safe suffix match."""
    model_caps = registry.get(model_name)
    if model_caps:
        return model_caps

    model_short = model_name.split('/')[-1] if '/' in model_name else model_name
    matches = [
        val for key, val in registry.items()
        if key.endswith(model_short) and val.get("enabled", True) is not False
    ]
    if len(matches) == 1:
        return matches[0]

    return None


def is_model_selectable(model_caps: Dict) -> bool:
    """Return whether a model should be shown/used by automatic routing."""
    if not model_caps:
        return False
    if model_caps.get("enabled", True) is False:
        return False
    if model_caps.get("selectable", True) is False:
        return False
    live_status = str(model_caps.get("live_probe_status", "")).lower()
    return not any(marker in live_status for marker in BAD_LIVE_STATUS_MARKERS)


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


def is_model_compatible(model_name: str, task_type: str, full_caps: Dict) -> bool:
    """Check if model is compatible with task type."""
    registry = full_caps.get("registry", {})
    model_caps = resolve_model_caps(model_name, registry)
    
    if not is_model_selectable(model_caps):
        # Unknown models are assumed to NOT support parallel tools for safety
        return False
    
    # Check if model is disabled for this task type
    disabled_for = model_caps.get("disabled_for", [])
    if "all" in disabled_for or task_type in disabled_for:
        return False
    
    # Check task requirements
    task_reqs = full_caps.get("task_requirements", {}).get(task_type, {})
    required_caps = task_reqs.get("requires", [])
    
    for cap in required_caps:
        if not model_caps.get(cap, False):
            return False
    
    return True


def get_selectable_models(
    provider: Optional[str] = None,
    task_type: Optional[str] = None,
) -> List[str]:
    """Return models that are safe to show in model menus."""
    full_caps = load_capabilities_full()
    registry = full_caps.get("registry", {})
    models = []
    for model_name, model_caps in registry.items():
        if provider and model_caps.get("provider") != provider:
            continue
        if not is_model_selectable(model_caps):
            continue
        if task_type and not is_model_compatible(model_name, task_type, full_caps):
            continue
        models.append(model_name)
    return sorted(models)


def select_model(
    task_type: str,
    primary_model: str,
    fallback_models: List[str],
    primary_available: bool,
    openrouter_credits: Optional[float] = None,
    max_cost_per_task: Optional[float] = None
) -> Optional[str]:
    """
    Select best model for task with cost awareness.
    
    Args:
        task_type: Type of task (tool_heavy, multi_tool, planning, summarization)
        primary_model: Primary model to try first
        fallback_models: List of fallback models
        primary_available: Whether primary model is available
        openrouter_credits: Available OpenRouter credits
        max_cost_per_task: Maximum cost per task (USD)
    
    Returns:
        Selected model name or None if no compatible model found
    """
    full_caps = load_capabilities_full()
    registry = full_caps.get("registry", {})
    
    # Try primary model first
    if primary_available:
        if is_model_compatible(primary_model, task_type, full_caps):
            primary_caps = resolve_model_caps(primary_model, registry)
            
            # Check credits if needed
            if primary_caps and primary_caps.get("cost_tier") == "paid":
                min_credits = primary_caps.get("min_credits_required", 0)
                if openrouter_credits is not None and openrouter_credits < min_credits:
                    # Insufficient credits, try fallback
                    pass
                else:
                    # Check cost limit
                    if max_cost_per_task is not None:
                        estimated_cost = primary_caps.get("estimated_cost_per_task", 0)
                        if estimated_cost > max_cost_per_task:
                            # Too expensive, try fallback
                            pass
                        else:
                            return primary_model
                    else:
                        return primary_model
            else:
                return primary_model
    
    # Try fallback models
    for fallback in fallback_models:
        if is_model_compatible(fallback, task_type, full_caps):
            fallback_caps = resolve_model_caps(fallback, registry)
            
            if not fallback_caps: 
                continue
            
            # Check credits if needed
            if fallback_caps.get("cost_tier") == "paid":
                min_credits = fallback_caps.get("min_credits_required", 0)
                if openrouter_credits is not None and openrouter_credits < min_credits:
                    continue
            
            # Check cost limit
            if max_cost_per_task is not None:
                estimated_cost = fallback_caps.get("estimated_cost_per_task", 0)
                if estimated_cost > max_cost_per_task:
                    continue
            
            return fallback
    
    # No compatible model found - return None for safe mode
    return None


def should_use_single_tool_mode(model_name: str) -> bool:
    """Check if model requires single tool mode."""
    try:
        full_caps = load_capabilities_full()
        registry = full_caps.get("registry", {})
        
        model_caps = resolve_model_caps(model_name, registry)
        
        return (
            model_caps.get("single_tool_mode_required", False)
            if is_model_selectable(model_caps)
            else False
        )
    except:
        return False


def get_safe_mode_action(reason: str) -> Dict:
    """
    Get safe mode action when no compatible model available.
    
    Args:
        reason: Reason for entering safe mode
    
    Returns:
        Dict with action details
    """
    return {
        "action": "pause_and_notify",
        "reason": reason,
        "message": f"Task paused: {reason}. Will resume when compatible model available.",
        "retry_after": 300,  # 5 minutes
        "notification": True
    }


def handle_provider_error(error: Exception, context: Dict) -> Dict:
    """
    Handle provider errors with appropriate recovery action.
    
    Args:
        error: The exception that occurred
        context: Context including provider, task_type, etc.
    
    Returns:
        Dict with recovery action
    """
    error_str = str(error).lower()
    
    # HTTP 400 - Bad Request (incompatible model)
    if "400" in error_str or "bad request" in error_str:
        if "single tool" in error_str or "parallel" in error_str:
            return {
                "action": "safe_mode",
                "reason": "incompatible_model",
                "should_retry": False,
                "message": "Model incompatible with task requirements"
            }
    
    # HTTP 429 - Rate Limit
    if "429" in error_str or "rate limit" in error_str:
        return {
            "action": "pause_and_retry",
            "reason": "rate_limit",
            "should_retry": True,
            "retry_after": 60,  # 1 minute
            "message": "Rate limit exceeded, will retry with fallback"
        }
    
    # HTTP 503 - Service Unavailable
    if "503" in error_str or "unavailable" in error_str:
        return {
            "action": "try_fallback",
            "reason": "provider_unavailable",
            "should_retry": True,
            "retry_after": 30,
            "message": "Provider unavailable, trying fallback"
        }
    
    # Connection errors
    if "connection" in error_str or "timeout" in error_str:
        return {
            "action": "try_fallback",
            "reason": "connection_error",
            "should_retry": True,
            "retry_after": 10,
            "message": "Connection error, trying fallback"
        }
    
    # Unknown error - safe mode
    return {
        "action": "safe_mode",
        "reason": "unknown_error",
        "should_retry": False,
        "message": f"Unknown error: {error}"
    }


if __name__ == "__main__":
    # Test
    try:
        full_caps = load_capabilities_full()
        print("Model Capabilities Registry loaded")
        print(f"Models in registry: {len(full_caps['registry'])}")
        
        # Test selection
        result = select_model(
            task_type="multi_tool",
            primary_model="anthropic/claude-sonnet-4",
            fallback_models=[
                "meta/llama-3.3-70b-instruct",
                "nvidia/nemotron-3-super-120b-a12b:free"
            ],
            primary_available=False,
            openrouter_credits=None
        )
        print(f"\nTest multi_tool task with primary unavailable:")
        print(f"Selected: {result}")
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
