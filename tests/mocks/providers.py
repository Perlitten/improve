"""Mock provider implementations for testing"""

from typing import Optional, List, Dict, Any


class MockResponse:
    """Mock LLM response"""
    
    def __init__(self, content: str, model: str = "test-model", tokens: int = 100):
        self.content = content
        self.model = model
        self.tokens = tokens
        self.choices = [{"message": {"content": content}}]
        
    def __str__(self):
        return self.content


class MockProvider:
    """Base mock provider"""
    
    def __init__(self, name: str, responses: Optional[List[str]] = None):
        self.name = name
        self.responses = responses or ["Mock response"]
        self.call_count = 0
        self.calls = []
        self.should_fail = False
        self.failure_error = Exception("Provider failed")
        
    def chat_completion(self, messages: List[Dict], **kwargs) -> MockResponse:
        """Mock chat completion"""
        self.calls.append({
            "messages": messages,
            "kwargs": kwargs
        })
        
        if self.should_fail:
            self.call_count += 1
            raise self.failure_error
        
        response_text = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        
        return MockResponse(
            content=response_text,
            model=kwargs.get("model", "test-model"),
            tokens=len(response_text.split())
        )
    
    def fail(self, error: Optional[Exception] = None):
        """Make provider fail"""
        self.should_fail = True
        if error:
            self.failure_error = error
    
    def succeed(self):
        """Make provider succeed"""
        self.should_fail = False
    
    def reset(self):
        """Reset provider state"""
        self.call_count = 0
        self.calls = []
        self.should_fail = False


class MockOpenRouterProvider(MockProvider):
    """Mock OpenRouter provider"""
    
    def __init__(self, responses: Optional[List[str]] = None):
        super().__init__("openrouter", responses)


class MockNVIDIAProvider(MockProvider):
    """Mock NVIDIA provider"""
    
    def __init__(self, responses: Optional[List[str]] = None):
        super().__init__("nvidia", responses)


class MockProviderManager:
    """Mock provider manager for testing"""
    
    def __init__(self):
        self.openrouter = MockOpenRouterProvider()
        self.nvidia = MockNVIDIAProvider()
        self.providers = {
            "openrouter": self.openrouter,
            "nvidia": self.nvidia
        }
    
    def get_provider(self, name: str) -> MockProvider:
        """Get provider by name"""
        return self.providers.get(name)
    
    def reset_all(self):
        """Reset all providers"""
        for provider in self.providers.values():
            provider.reset()
