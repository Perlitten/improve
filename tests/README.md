# Hermes Test Suite

**Test Coverage Target:** 80%+  
**Current Coverage:** See badge below

## 🎯 Test Structure

```
tests/
├── unit/           # Unit tests (fast, isolated)
├── integration/    # Integration tests (component interactions)
├── e2e/            # End-to-end tests (full user flows)
├── fixtures/       # Test fixtures
├── mocks/          # Mock objects
└── conftest.py     # Shared pytest configuration
```

## 🚀 Running Tests

### All Tests

```bash
cd hermes
pytest
```

### Unit Tests Only

```bash
pytest tests/unit -v
```

### Integration Tests Only

```bash
pytest tests/integration -v
```

### E2E Tests Only

```bash
pytest tests/e2e -v -m e2e
```

### With Coverage

```bash
pytest --cov=src --cov-report=html
```

View coverage report: `open htmlcov/index.html`

### Specific Test File

```bash
pytest tests/unit/test_model_router.py -v
```

### Specific Test Function

```bash
pytest tests/unit/test_model_router.py::TestModelRouter::test_select_model_primary_available -v
```

## 🏷️ Test Markers

Tests are marked with pytest markers for selective execution:

- `@pytest.mark.unit` — Unit tests (fast, < 100ms)
- `@pytest.mark.integration` — Integration tests (medium, < 1s)
- `@pytest.mark.e2e` — End-to-end tests (slow, > 1s)
- `@pytest.mark.slow` — Slow tests (> 5s)

### Run Only Fast Tests

```bash
pytest -m "not slow"
```

### Run Only Integration Tests

```bash
pytest -m integration
```

## 📦 Installation

### Install Test Dependencies

```bash
pip install -r requirements-test.txt
```

### Or Install in Development Mode

```bash
pip install -e ".[test]"
```

## 🧪 Writing Tests

### Unit Test Example

```python
import pytest
from src.model_router import select_model

@pytest.mark.unit
def test_select_model_primary_available(sample_capabilities):
    result = select_model(
        task_type="multi_tool",
        primary_model="anthropic/claude-sonnet-4",
        fallback_models=["nvidia/nemotron"],
        primary_available=True
    )
    
    assert result == "anthropic/claude-sonnet-4"
```

### Integration Test Example

```python
import pytest

@pytest.mark.integration
def test_provider_fallback_chain(mock_providers):
    # Primary fails → fallback succeeds
    mock_providers.openrouter.fail()
    mock_providers.nvidia.succeed()
    
    result = execute_task_with_routing(
        task="Test task",
        task_type="multi_tool"
    )
    
    assert result.success == True
    assert result.provider == "nvidia"
```

### E2E Test Example

```python
import pytest

@pytest.mark.e2e
@pytest.mark.slow
def test_complete_task_flow():
    # User sends message → Task queued → Processed → Response
    response = send_telegram_message("What's 2+2?")
    assert response["status"] == "queued"
    
    wait_for_task_completion(response["task_id"])
    
    result = get_task_result(response["task_id"])
    assert "4" in result["response"]
```

## 🔧 Fixtures

### Available Fixtures

- `test_config` — Test configuration
- `mock_env` — Mock environment variables
- `sample_capabilities` — Sample model capabilities
- `mock_providers` — Mock provider manager
- `clean_db` — Clean test database

### Using Fixtures

```python
def test_with_fixtures(test_config, mock_env, sample_capabilities):
    # Fixtures are automatically injected
    assert test_config["test_mode"] == True
    assert "HERMES_HOME" in mock_env
    assert "registry" in sample_capabilities
```

## 📊 Coverage Goals

| Component | Target | Current |
|-----------|--------|---------|
| model_router.py | 90% | TBD |
| brain_mcp_server.py | 85% | TBD |
| canonical_memory.py | 85% | TBD |
| task_orchestrator.py | 90% | TBD |
| Overall | 80% | TBD |

## 🐛 Debugging Tests

### Run with Verbose Output

```bash
pytest -vv
```

### Run with Print Statements

```bash
pytest -s
```

### Run with Debugger

```bash
pytest --pdb
```

### Run Failed Tests Only

```bash
pytest --lf
```

## 📝 Best Practices

1. **Keep tests fast** — Unit tests should run in < 100ms
2. **Use fixtures** — Reuse test setup via fixtures
3. **Mock external dependencies** — Don't call real APIs in tests
4. **Test one thing** — Each test should verify one behavior
5. **Use descriptive names** — Test names should describe what they test
6. **Arrange-Act-Assert** — Structure tests clearly
7. **Don't test implementation** — Test behavior, not internals

## 🚨 CI/CD Integration

Tests run automatically on:
- Every commit (unit tests)
- Every PR (unit + integration tests)
- Before deployment (all tests)

### Required Checks

- ✅ All tests pass
- ✅ Coverage > 80%
- ✅ No flake8 errors
- ✅ No mypy errors

## 📚 Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [Testing best practices](https://docs.python-guide.org/writing/tests/)

---

**Status:** Test framework ready ✅  
**Last Updated:** 2026-05-05
