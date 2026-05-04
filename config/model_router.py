#!/usr/bin/env python3
"""
Capability-aware model router.
Selects model based on task requirements and model capabilities.
"""

import json
from pathlib import Path
from typing import Optional, Dict, List

CAPABILITIES_PATH = Path("/home/Bilirubin/.hermes/model_capabilities.json")


def load_capabilities_full() -> Dict:
    """Load full model capabilities file."""
    if not CAPABILITIES_PATH.exists():
        # Fallback to local path if running in tests
        local_path = Path(__file__).parent.parent / "maintenance/model_capabilities.json"
        if not local_path.exists():
             local_path = Path(__file__).parent / "model_capabilities.json"
        
        if local_path.exists():
            return json.loads(local_path.read_text())
        return {"registry": {}, "task_requirements": {}}
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


def is_model_compatible(model_name: str, task_type: str, full_caps: Dict) -> bool:
    """Check if model is compatible with task type."""
    registry = full_caps.get("registry", {})
    model_caps = registry.get(model_name)
    
    if not model_caps:
        # Try finding by name without provider prefix
        model_short = model_name.split('/')[-1] if '/' in model_name else model_name
        for key, val in registry.items():
            if key.endswith(model_short):
                model_caps = val
                break
    
    if not model_caps:
        # Unknown models are assumed to NOT support parallel tools for safety
        return False
    
    # Check if model is disabled for this task type
    if task_type in model_caps.get("disabled_for", []):
        return False
    
    # Check task requirements
    task_reqs = full_caps.get("task_requirements", {}).get(task_type, {})
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
    """
    full_caps = load_capabilities_full()
    registry = full_caps.get("registry", {})
    
    # Try primary model first
    if primary_available:
        if is_model_compatible(primary_model, task_type, full_caps):
            # Check credits if needed
            primary_caps = registry.get(primary_model)
            if primary_caps and primary_caps.get("cost_tier") == "paid":
                min_credits = primary_caps.get("min_credits_required", 0)
                if openrouter_credits is None or openrouter_credits >= min_credits:
                    return primary_model
            else:
                return primary_model
    
    # Try fallback models
    for fallback in fallback_models:
        if is_model_compatible(fallback, task_type, full_caps):
            fallback_caps = registry.get(fallback)
            if not fallback_caps:
                 # Re-find if it was a short name match in is_model_compatible
                 model_short = fallback.split('/')[-1] if '/' in fallback else fallback
                 for key, val in registry.items():
                     if key.endswith(model_short):
                         fallback_caps = val
                         break
            
            if not fallback_caps: continue
            
            # Check credits if needed
            if fallback_caps.get("cost_tier") == "paid":
                min_credits = fallback_caps.get("min_credits_required", 0)
                if openrouter_credits is not None and openrouter_credits < min_credits:
                    continue
            
            return fallback
    
    # No compatible model found
    return None


def should_use_single_tool_mode(model_name: str) -> bool:
    """Check if model requires single tool mode."""
    try:
        full_caps = load_capabilities_full()
        registry = full_caps.get("registry", {})
        
        model_caps = registry.get(model_name)
        if not model_caps:
             model_short = model_name.split('/')[-1] if '/' in model_name else model_name
             for key, val in registry.items():
                 if key.endswith(model_short):
                     model_caps = val
                     break
        
        return model_caps.get("single_tool_mode_required", False) if model_caps else False
    except:
        return False


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
