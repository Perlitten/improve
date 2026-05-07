"""Unit tests for model_router.py"""

import pytest
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from model_router import (
    select_model,
    is_model_compatible,
    should_use_single_tool_mode,
    get_selectable_models,
    get_task_type
)


@pytest.mark.unit
class TestModelRouter:
    """Test model router functionality"""
    
    def test_select_model_primary_available(self, sample_capabilities, monkeypatch):
        """Test model selection when primary is available"""
        # Mock load_capabilities_full
        import model_router
        monkeypatch.setattr(model_router, "load_capabilities_full", lambda: sample_capabilities)
        
        result = select_model(
            task_type="multi_tool",
            primary_model="anthropic/claude-sonnet-4",
            fallback_models=["nvidia/nemotron-3-super-120b-a12b:free"],
            primary_available=True,
            openrouter_credits=5.0
        )
        
        assert result == "anthropic/claude-sonnet-4"
    
    def test_select_model_fallback_when_primary_unavailable(self, sample_capabilities, monkeypatch):
        """Test fallback when primary unavailable"""
        import model_router
        monkeypatch.setattr(model_router, "load_capabilities_full", lambda: sample_capabilities)
        
        result = select_model(
            task_type="multi_tool",
            primary_model="anthropic/claude-sonnet-4",
            fallback_models=["deepseek/deepseek-v4-flash"],
            primary_available=False
        )
        
        assert result == "deepseek/deepseek-v4-flash"
    
    def test_select_model_insufficient_credits(self, sample_capabilities, monkeypatch):
        """Test fallback when insufficient credits"""
        import model_router
        monkeypatch.setattr(model_router, "load_capabilities_full", lambda: sample_capabilities)
        
        result = select_model(
            task_type="multi_tool",
            primary_model="anthropic/claude-sonnet-4",
            fallback_models=["qwen/qwen3-next-80b-a3b-instruct"],
            primary_available=True,
            openrouter_credits=0.5  # Less than min_credits_required (1.5)
        )
        
        # Should fallback to free model
        assert result == "qwen/qwen3-next-80b-a3b-instruct"
    
    def test_is_model_compatible_parallel_tools(self, sample_capabilities):
        """Test compatibility check for parallel tools"""
        result = is_model_compatible(
            model_name="anthropic/claude-sonnet-4",
            task_type="multi_tool",
            full_caps=sample_capabilities
        )
        
        assert result == True
    
    def test_is_model_incompatible_parallel_tools(self, sample_capabilities):
        """Test incompatibility for models without parallel tools"""
        result = is_model_compatible(
            model_name="meta/llama-3.3-70b-instruct",
            task_type="multi_tool",
            full_caps=sample_capabilities
        )
        
        assert result == False
    
    def test_is_model_compatible_planning_task(self, sample_capabilities):
        """Test compatibility for planning tasks (no special requirements)"""
        result = is_model_compatible(
            model_name="meta/llama-3.3-70b-instruct",
            task_type="planning",
            full_caps=sample_capabilities
        )
        
        assert result == True
    
    def test_should_use_single_tool_mode_true(self, sample_capabilities, monkeypatch):
        """Test single tool mode detection"""
        import model_router
        monkeypatch.setattr(model_router, "load_capabilities_full", lambda: sample_capabilities)
        
        result = should_use_single_tool_mode("meta/llama-3.3-70b-instruct")
        
        assert result == True
    
    def test_should_use_single_tool_mode_false(self, sample_capabilities, monkeypatch):
        """Test single tool mode not required"""
        import model_router
        monkeypatch.setattr(model_router, "load_capabilities_full", lambda: sample_capabilities)
        
        result = should_use_single_tool_mode("anthropic/claude-sonnet-4")
        
        assert result == False

    def test_disabled_rate_limited_model_is_not_compatible(self, sample_capabilities):
        """Test disabled live-probe failures are excluded from routing."""
        result = is_model_compatible(
            model_name="google/gemma-4-26b-a4b-it:free",
            task_type="planning",
            full_caps=sample_capabilities
        )

        assert result == False

    def test_single_tool_model_not_used_for_multi_tool(self, sample_capabilities):
        """Test single-tool fallbacks are not used for multi-tool tasks."""
        result = is_model_compatible(
            model_name="nvidia/nemotron-3-super-120b-a12b:free",
            task_type="multi_tool",
            full_caps=sample_capabilities
        )

        assert result == False

    def test_get_selectable_models_filters_disabled(self, sample_capabilities, monkeypatch):
        """Test menu-safe model list hides disabled models."""
        import model_router
        monkeypatch.setattr(model_router, "load_capabilities_full", lambda: sample_capabilities)

        models = get_selectable_models(provider="openrouter")

        assert "anthropic/claude-sonnet-4" in models
        assert "google/gemma-4-26b-a4b-it:free" not in models
    
    def test_get_task_type_multi_tool(self):
        """Test task type detection for multi-tool tasks"""
        context = {
            "expected_tool_calls": 3,
            "task_description": "Analyze data and generate report"
        }
        
        result = get_task_type(context)
        
        assert result == "multi_tool"
    
    def test_get_task_type_tool_heavy(self):
        """Test task type detection for tool-heavy tasks"""
        context = {
            "requires_tools": True,
            "expected_tool_calls": 1,
            "task_description": "Search database"
        }
        
        result = get_task_type(context)
        
        assert result == "tool_heavy"
    
    def test_get_task_type_planning(self):
        """Test task type detection for planning tasks"""
        context = {
            "task_description": "Create a plan for project"
        }
        
        result = get_task_type(context)
        
        assert result == "planning"
    
    def test_select_model_no_compatible_fallback(self, sample_capabilities, monkeypatch):
        """Test when no compatible fallback exists"""
        import model_router
        monkeypatch.setattr(model_router, "load_capabilities_full", lambda: sample_capabilities)
        
        result = select_model(
            task_type="multi_tool",
            primary_model="anthropic/claude-sonnet-4",
            fallback_models=["meta/llama-3.3-70b-instruct"],  # Incompatible
            primary_available=False
        )
        
        assert result is None
    
    def test_select_model_unknown_model(self, sample_capabilities, monkeypatch):
        """Test selection with unknown model"""
        import model_router
        monkeypatch.setattr(model_router, "load_capabilities_full", lambda: sample_capabilities)
        
        result = select_model(
            task_type="multi_tool",
            primary_model="unknown/model",
            fallback_models=["deepseek/deepseek-v4-flash"],
            primary_available=True
        )
        
        # Unknown models are assumed incompatible for safety
        assert result == "deepseek/deepseek-v4-flash"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
