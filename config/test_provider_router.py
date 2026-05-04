#!/usr/bin/env python3
"""
Acceptance tests for Phase 9.9: Provider Capability Router
"""

import sys
import os
from pathlib import Path

# Add script directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "maintenance"))

from model_router import (
    load_capabilities_full,
    is_model_compatible,
    select_model,
    should_use_single_tool_mode
)


def test_capability_registry_loads():
    """Test 1: Capability registry loads successfully."""
    full_caps = load_capabilities_full()
    assert "registry" in full_caps
    assert "task_requirements" in full_caps
    assert len(full_caps["registry"]) > 0
    print("✅ Test 1: Capability registry loads")


def test_llama_incompatible_with_multi_tool():
    """Test 2: NVIDIA llama is incompatible with multi_tool tasks."""
    full_caps = load_capabilities_full()
    compatible = is_model_compatible(
        "meta/llama-3.3-70b-instruct",
        "multi_tool",
        full_caps
    )
    assert not compatible, "llama should NOT be compatible with multi_tool"
    print("✅ Test 2: llama incompatible with multi_tool")


def test_nemotron_compatible_with_multi_tool():
    """Test 3: Nemotron is compatible with multi_tool tasks."""
    full_caps = load_capabilities_full()
    compatible = is_model_compatible(
        "nvidia/nemotron-3-super-120b-a12b:free",
        "multi_tool",
        full_caps
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
    
    # Ensure capabilities file is available for test (use local one if needed)
    caps_path = Path("/home/Bilirubin/.hermes/model_capabilities.json")
    if not caps_path.exists():
        # Create a dummy one for local testing
        dummy_caps = {
            "models": {
                "anthropic/claude-sonnet-4": {"supports_parallel_tool_calls": True, "cost_tier": "paid", "min_credits_required": 1.0},
                "nvidia/nemotron-3-super-120b-a12b:free": {"supports_parallel_tool_calls": True, "cost_tier": "free"},
                "meta/llama-3.3-70b-instruct": {"supports_parallel_tool_calls": False, "single_tool_mode_required": True, "disabled_for": ["multi_tool"]},
                "meta/llama-3.1-405b-instruct": {"supports_parallel_tool_calls": False, "disabled_for": ["multi_tool"]}
            },
            "task_requirements": {
                "multi_tool": {"requires": ["supports_parallel_tool_calls"]}
            }
        }
        # Note: In real test on server, it will use the actual file.
    
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
