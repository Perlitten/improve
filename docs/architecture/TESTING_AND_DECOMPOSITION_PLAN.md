# 🧪 Testing & Decomposition Plan

**Date:** 2026-05-05  
**Goal:** Increase test coverage + decompose monolithic modules  
**Timeline:** 2 weeks (parallel with cleanup)

---

## 🎯 Overview

### Current State

**Test Coverage:** ~5% (2 test files only)
- `test_nim.py` (1.1 KB) — NIM orchestrator tests
- `test_provider_router.py` (5.5 KB) — Provider router tests

**Monolithic Modules:**
- `run_loop.py` (233 KB, 3500+ lines) — CRITICAL MONOLITH
- `streaming_api.py` (95 KB)
- `prompting.py` (76 KB)
- `tool_executor.py` (63 KB)

### Target State

**Test Coverage:** 80%+
- Unit tests for all core modules
- Integration tests for critical paths
- End-to-end tests for user flows

**Modular Architecture:**
- `run_loop.py` → 8-10 smaller modules
- Clear separation of concerns
- Easy to test, easy to maintain

---

## 🔴 Critical Monolith: run_loop.py

### Current Structure

```python
# hermes/src/hermes_core/mixins/run_loop.py
# 233 KB, 3500+ lines, ONE METHOD

class RunLoopMixin:
    def run_conversation(self, ...):  # 3500+ lines!
        # Message handling
        # Tool execution
        # Provider routing
        # Error handling
        # Streaming
        # Checkpointing
        # Cost tracking
        # ... everything
```

### Problems

1. **Impossible to test** — too many responsibilities
2. **Hard to understand** — 3500 lines in one method
3. **Hard to modify** — change one thing, break everything
4. **No separation of concerns** — everything mixed together
5. **Performance issues** — no optimization possible

### Decomposition Strategy

Break into **8 focused modules:**

```
run_loop.py (233 KB)
    ↓
    ├── message_handler.py      # Message intake & validation
    ├── tool_orchestrator.py    # Tool execution coordination
    ├── provider_manager.py     # Provider selection & routing
    ├── stream_processor.py     # Streaming response handling
    ├── checkpoint_manager.py   # State persistence
    ├── error_handler.py        # Error recovery
    ├── cost_tracker.py         # Cost calculation & tracking
    └── conversation_loop.py    # Main loop (orchestrates above)
```

---

## 📋 Week 1: Testing Infrastructure

### Day 1: Test Framework Setup

**Goal:** Set up testing infrastructure

**Tasks:**

1. **Create test directory structure**
   ```bash
   mkdir -p hermes/tests/{unit,integration,e2e}
   mkdir -p hermes/tests/fixtures
   mkdir -p hermes/tests/mocks
   ```

2. **Set up pytest configuration**
   ```ini
   # hermes/pytest.ini
   
   [pytest]
   testpaths = tests
   python_files = test_*.py
   python_classes = Test*
   python_functions = test_*
   
   # Coverage settings
   addopts = 
       --cov=src
       --cov-report=html
       --cov-report=term-missing
       --cov-fail-under=80
       
   # Markers
   markers =
       unit: Unit tests
       integration: Integration tests
       e2e: End-to-end tests
       slow: Slow tests
   ```

3. **Install testing dependencies**
   ```bash
   pip install pytest pytest-cov pytest-asyncio pytest-mock
   pip install faker factory-boy
   ```

4. **Create test fixtures**
   ```python
   # hermes/tests/fixtures/database.py
   
   import pytest
   import psycopg2
   
   @pytest.fixture
   def test_db():
       """Create test database"""
       conn = psycopg2.connect(
           host="127.0.0.1",
           port=5432,
           dbname="rag_test",
           user="automation",
           password="test"
       )
       yield conn
       conn.close()
   
   @pytest.fixture
   def clean_db(test_db):
       """Clean database before each test"""
       cursor = test_db.cursor()
       cursor.execute("TRUNCATE agent_inbox, agent_tasks CASCADE")
       test_db.commit()
       yield test_db
   ```

5. **Create mock providers**
   ```python
   # hermes/tests/mocks/providers.py
   
   class MockOpenRouterProvider:
       def __init__(self, responses=None):
           self.responses = responses or []
           self.call_count = 0
           
       def chat_completion(self, messages, **kwargs):
           response = self.responses[self.call_count]
           self.call_count += 1
           return response
   
   class MockNVIDIAProvider:
       # Similar structure
   ```

**Success Criteria:**
- ✅ Test framework configured
- ✅ Fixtures created
- ✅ Mocks ready
- ✅ Can run `pytest` successfully

**Time:** 4 hours

---

### Day 2-3: Unit Tests for Core Modules

**Goal:** Test individual components

**Tasks:**

1. **Test model_router.py**
   ```python
   # hermes/tests/unit/test_model_router.py
   
   import pytest
   from src.model_router import select_model, is_model_compatible
   
   def test_select_model_primary_available():
       result = select_model(
           task_type="multi_tool",
           primary_model="anthropic/claude-sonnet-4",
           fallback_models=["nvidia/nemotron"],
           primary_available=True
       )
       assert result == "anthropic/claude-sonnet-4"
   
   def test_select_model_fallback_when_primary_unavailable():
       result = select_model(
           task_type="multi_tool",
           primary_model="anthropic/claude-sonnet-4",
           fallback_models=["nvidia/nemotron"],
           primary_available=False
       )
       assert result == "nvidia/nemotron"
   
   def test_incompatible_model_rejected():
       result = is_model_compatible(
           model_name="meta/llama-3.3-70b-instruct",
           task_type="multi_tool",
           full_caps=load_test_capabilities()
       )
       assert result == False
   
   # 20+ more tests
   ```

2. **Test brain_mcp_server.py**
   ```python
   # hermes/tests/unit/test_brain_mcp_server.py
   
   import pytest
   from src.brain_mcp_server import (
       infra_readiness,
       memory_overview,
       provider_health_check
   )
   
   def test_infra_readiness(mock_systemctl, mock_http):
       result = infra_readiness()
       assert result["ok"] == True
       assert "services" in result
       assert "endpoints" in result
   
   def test_memory_overview(test_db):
       result = memory_overview()
       assert result["ok"] == True
       assert "counts" in result
       assert "collections" in result
   
   def test_provider_health_check(mock_providers):
       result = provider_health_check()
       assert "openrouter" in result["providers"]
       assert "nvidia" in result["providers"]
   
   # 30+ more tests
   ```

3. **Test canonical_memory.py**
   ```python
   # hermes/tests/unit/test_canonical_memory.py
   
   import pytest
   from src.canonical_memory import (
       ensure_workspace,
       ensure_project,
       record_insight
   )
   
   def test_ensure_workspace_creates_new(clean_db):
       cursor = clean_db.cursor()
       workspace_id = ensure_workspace(
           cursor,
           slug="test_workspace",
           name="Test Workspace"
       )
       assert workspace_id is not None
   
   def test_ensure_workspace_returns_existing(clean_db):
       cursor = clean_db.cursor()
       id1 = ensure_workspace(cursor, "test", "Test")
       id2 = ensure_workspace(cursor, "test", "Test")
       assert id1 == id2
   
   # 20+ more tests
   ```

4. **Test task_orchestrator.py** (to be created)
   ```python
   # hermes/tests/unit/test_task_orchestrator.py
   
   import pytest
   from src.task_orchestrator import TaskOrchestrator
   
   def test_enqueue_task(clean_db):
       orchestrator = TaskOrchestrator()
       task_id = orchestrator.enqueue(
           message="Test task",
           source="test",
           priority=5
       )
       assert task_id is not None
   
   def test_dequeue_task(clean_db):
       orchestrator = TaskOrchestrator()
       task_id = orchestrator.enqueue("Test", "test")
       task = orchestrator.dequeue()
       assert task["id"] == task_id
   
   def test_checkpoint_task(clean_db):
       orchestrator = TaskOrchestrator()
       task_id = orchestrator.enqueue("Test", "test")
       orchestrator.checkpoint(task_id, {"step": 1})
       # Verify checkpoint saved
   
   # 30+ more tests
   ```

**Success Criteria:**
- ✅ 100+ unit tests written
- ✅ Core modules covered
- ✅ All tests pass
- ✅ Coverage > 60%

**Time:** 12 hours

---

### Day 4: Integration Tests

**Goal:** Test component interactions

**Tasks:**

1. **Test provider routing flow**
   ```python
   # hermes/tests/integration/test_provider_routing.py
   
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
   
   @pytest.mark.integration
   def test_graceful_degradation_to_safe_mode(mock_providers):
       # All providers fail → safe mode
       mock_providers.openrouter.fail()
       mock_providers.nvidia.fail()
       
       result = execute_task_with_routing(
           task="Test task",
           task_type="multi_tool"
       )
       
       assert result.status == "paused"
       assert result.reason == "no_compatible_provider"
   ```

2. **Test task queue flow**
   ```python
   # hermes/tests/integration/test_task_queue.py
   
   @pytest.mark.integration
   def test_task_lifecycle(clean_db):
       # Enqueue → Process → Complete
       orchestrator = TaskOrchestrator()
       
       task_id = orchestrator.enqueue("Test", "test")
       task = orchestrator.dequeue()
       
       # Process task
       result = process_task(task)
       
       orchestrator.complete(task_id, result, cost=0.01)
       
       # Verify completion
       status = orchestrator.get_status(task_id)
       assert status == "completed"
   
   @pytest.mark.integration
   def test_checkpoint_and_resume(clean_db):
       # Start → Checkpoint → Restart → Resume → Complete
       orchestrator = TaskOrchestrator()
       
       task_id = orchestrator.enqueue("Long task", "test")
       task = orchestrator.dequeue()
       
       # Process partially
       orchestrator.checkpoint(task_id, {"step": 1, "data": "..."})
       
       # Simulate restart
       orchestrator = TaskOrchestrator()
       
       # Resume
       task = orchestrator.resume(task_id)
       assert task["checkpoint_data"]["step"] == 1
   ```

3. **Test MCP control plane**
   ```python
   # hermes/tests/integration/test_mcp_control_plane.py
   
   @pytest.mark.integration
   def test_mcp_infra_readiness():
       # Real MCP call (requires brain-mcp running)
       result = call_mcp_tool("infra_readiness")
       
       assert result["ok"] == True
       assert "services" in result
       assert "memory" in result
   
   @pytest.mark.integration
   def test_mcp_memory_search():
       # Store document → Search → Verify
       call_mcp_tool("memory_record_observation", {
           "title": "Test observation",
           "content": "Test content"
       })
       
       result = call_mcp_tool("memory_search", {
           "collection": "agent-observations",
           "query": "Test observation"
       })
       
       assert result["count"] > 0
   ```

**Success Criteria:**
- ✅ 30+ integration tests
- ✅ Critical paths covered
- ✅ All tests pass
- ✅ Coverage > 70%

**Time:** 6 hours

---

### Day 5: E2E Tests

**Goal:** Test complete user flows

**Tasks:**

1. **Test complete task execution**
   ```python
   # hermes/tests/e2e/test_task_execution.py
   
   @pytest.mark.e2e
   @pytest.mark.slow
   def test_complete_task_flow():
       # User sends message → Task queued → Processed → Response
       
       # 1. Send message
       response = send_telegram_message("What's 2+2?")
       assert response["status"] == "queued"
       task_id = response["task_id"]
       
       # 2. Wait for processing
       wait_for_task_completion(task_id, timeout=60)
       
       # 3. Verify result
       result = get_task_result(task_id)
       assert result["status"] == "completed"
       assert "4" in result["response"]
   
   @pytest.mark.e2e
   @pytest.mark.slow
   def test_task_survives_restart():
       # Start task → Checkpoint → Restart → Resume → Complete
       
       # 1. Start long task
       task_id = send_telegram_message("Long calculation...")
       
       # 2. Wait for checkpoint
       wait_for_checkpoint(task_id)
       
       # 3. Restart hermes-gateway
       restart_service("hermes-gateway")
       
       # 4. Verify task resumes
       wait_for_task_completion(task_id, timeout=120)
       
       result = get_task_result(task_id)
       assert result["status"] == "completed"
   ```

2. **Test provider failover**
   ```python
   # hermes/tests/e2e/test_provider_failover.py
   
   @pytest.mark.e2e
   @pytest.mark.slow
   def test_provider_failover_flow():
       # Primary fails → Fallback succeeds → Task completes
       
       # 1. Simulate primary provider failure
       simulate_provider_failure("openrouter")
       
       # 2. Send task
       task_id = send_telegram_message("Test task")
       
       # 3. Verify fallback used
       wait_for_task_completion(task_id)
       result = get_task_result(task_id)
       
       assert result["provider"] == "nvidia"
       assert result["status"] == "completed"
   ```

3. **Test cost tracking**
   ```python
   # hermes/tests/e2e/test_cost_tracking.py
   
   @pytest.mark.e2e
   def test_cost_tracking_flow():
       # Execute tasks → Track costs → Verify budget
       
       # 1. Execute multiple tasks
       task_ids = []
       for i in range(10):
           task_id = send_telegram_message(f"Task {i}")
           task_ids.append(task_id)
       
       # 2. Wait for completion
       for task_id in task_ids:
           wait_for_task_completion(task_id)
       
       # 3. Verify costs tracked
       daily_cost = get_daily_cost()
       assert daily_cost > 0
       
       # 4. Verify budget alert
       if daily_cost > get_daily_budget() * 0.80:
           assert alert_was_sent("budget_warning")
   ```

**Success Criteria:**
- ✅ 10+ E2E tests
- ✅ User flows covered
- ✅ All tests pass
- ✅ Coverage > 75%

**Time:** 6 hours

---

## 📋 Week 2: Decomposition

### Day 6-7: Decompose run_loop.py

**Goal:** Break monolith into modules

**Tasks:**

1. **Extract MessageHandler**
   ```python
   # hermes/src/hermes_core/message_handler.py
   
   class MessageHandler:
       """Handle message intake and validation"""
       
       def validate_message(self, message: str) -> bool:
           """Validate message format"""
           
       def parse_message(self, message: str) -> dict:
           """Parse message into structured format"""
           
       def classify_message(self, message: str) -> str:
           """Classify message type (task, question, command)"""
   ```

2. **Extract ToolOrchestrator**
   ```python
   # hermes/src/hermes_core/tool_orchestrator.py
   
   class ToolOrchestrator:
       """Coordinate tool execution"""
       
       def select_tools(self, task: dict) -> list:
           """Select appropriate tools for task"""
           
       def execute_tool(self, tool: str, args: dict) -> dict:
           """Execute single tool"""
           
       def execute_parallel(self, tools: list) -> list:
           """Execute multiple tools in parallel"""
           
       def handle_tool_error(self, error: Exception) -> dict:
           """Handle tool execution errors"""
   ```

3. **Extract ProviderManager**
   ```python
   # hermes/src/hermes_core/provider_manager.py
   
   class ProviderManager:
       """Manage provider selection and routing"""
       
       def select_provider(self, task_type: str) -> str:
           """Select best provider for task"""
           
       def get_fallback_chain(self, primary: str) -> list:
           """Get fallback providers"""
           
       def check_provider_health(self, provider: str) -> bool:
           """Check if provider is healthy"""
           
       def handle_provider_error(self, error: Exception) -> str:
           """Handle provider errors, return fallback"""
   ```

4. **Extract StreamProcessor**
   ```python
   # hermes/src/hermes_core/stream_processor.py
   
   class StreamProcessor:
       """Handle streaming responses"""
       
       def process_stream(self, stream, callback) -> str:
           """Process streaming response"""
           
       def handle_stream_error(self, error: Exception):
           """Handle streaming errors"""
           
       def accumulate_response(self, chunks: list) -> str:
           """Accumulate response from chunks"""
   ```

5. **Extract CheckpointManager**
   ```python
   # hermes/src/hermes_core/checkpoint_manager.py
   
   class CheckpointManager:
       """Manage task checkpoints"""
       
       def create_checkpoint(self, task_id: int, state: dict):
           """Create checkpoint"""
           
       def load_checkpoint(self, task_id: int) -> dict:
           """Load checkpoint"""
           
       def delete_checkpoint(self, task_id: int):
           """Delete checkpoint after completion"""
   ```

6. **Extract ErrorHandler**
   ```python
   # hermes/src/hermes_core/error_handler.py
   
   class ErrorHandler:
       """Handle errors and recovery"""
       
       def handle_error(self, error: Exception, context: dict) -> dict:
           """Handle error, return recovery action"""
           
       def should_retry(self, error: Exception) -> bool:
           """Determine if error is retryable"""
           
       def get_retry_delay(self, attempt: int) -> int:
           """Calculate retry delay (exponential backoff)"""
   ```

7. **Extract CostTracker**
   ```python
   # hermes/src/hermes_core/cost_tracker.py
   
   class CostTracker:
       """Track costs"""
       
       def calculate_cost(self, model: str, tokens: int) -> float:
           """Calculate cost for model and tokens"""
           
       def record_cost(self, task_id: int, cost: float):
           """Record cost in database"""
           
       def get_daily_cost(self) -> float:
           """Get total cost for today"""
           
       def check_budget(self) -> dict:
           """Check if budget exceeded"""
   ```

8. **Create new ConversationLoop**
   ```python
   # hermes/src/hermes_core/conversation_loop.py
   
   class ConversationLoop:
       """Main conversation loop (orchestrates all above)"""
       
       def __init__(self):
           self.message_handler = MessageHandler()
           self.tool_orchestrator = ToolOrchestrator()
           self.provider_manager = ProviderManager()
           self.stream_processor = StreamProcessor()
           self.checkpoint_manager = CheckpointManager()
           self.error_handler = ErrorHandler()
           self.cost_tracker = CostTracker()
       
       def run_conversation(self, message: str) -> str:
           """Main loop (now ~200 lines instead of 3500)"""
           
           # 1. Validate message
           if not self.message_handler.validate_message(message):
               return "Invalid message"
           
           # 2. Parse and classify
           parsed = self.message_handler.parse_message(message)
           task_type = self.message_handler.classify_message(message)
           
           # 3. Select provider
           provider = self.provider_manager.select_provider(task_type)
           
           # 4. Execute with error handling
           try:
               result = self._execute_with_provider(provider, parsed)
               
               # 5. Track cost
               cost = self.cost_tracker.calculate_cost(
                   provider, result.tokens
               )
               self.cost_tracker.record_cost(task_id, cost)
               
               return result.response
               
           except Exception as e:
               # 6. Handle error
               recovery = self.error_handler.handle_error(e, {
                   "provider": provider,
                   "task_type": task_type
               })
               
               if recovery["action"] == "retry":
                   # Retry with fallback
                   fallback = self.provider_manager.get_fallback_chain(provider)[0]
                   return self._execute_with_provider(fallback, parsed)
               else:
                   # Checkpoint and pause
                   self.checkpoint_manager.create_checkpoint(task_id, parsed)
                   return "Task paused, will resume later"
   ```

**Success Criteria:**
- ✅ 8 new modules created
- ✅ run_loop.py reduced to ~200 lines
- ✅ Clear separation of concerns
- ✅ All existing tests still pass

**Time:** 12 hours

---

### Day 8-9: Test Decomposed Modules

**Goal:** Test new modules

**Tasks:**

1. **Test MessageHandler**
   ```python
   # hermes/tests/unit/test_message_handler.py
   
   def test_validate_message():
       handler = MessageHandler()
       assert handler.validate_message("Valid message") == True
       assert handler.validate_message("") == False
   
   def test_parse_message():
       handler = MessageHandler()
       result = handler.parse_message("What's 2+2?")
       assert result["type"] == "question"
       assert "2+2" in result["content"]
   
   # 20+ more tests
   ```

2. **Test ToolOrchestrator**
   ```python
   # hermes/tests/unit/test_tool_orchestrator.py
   
   def test_select_tools():
       orchestrator = ToolOrchestrator()
       tools = orchestrator.select_tools({
           "type": "calculation",
           "content": "2+2"
       })
       assert "calculator" in tools
   
   def test_execute_parallel():
       orchestrator = ToolOrchestrator()
       results = orchestrator.execute_parallel([
           {"tool": "tool1", "args": {}},
           {"tool": "tool2", "args": {}}
       ])
       assert len(results) == 2
   
   # 30+ more tests
   ```

3. **Test all other modules** (similar structure)

**Success Criteria:**
- ✅ 100+ tests for new modules
- ✅ All modules covered
- ✅ Coverage > 80%
- ✅ All tests pass

**Time:** 12 hours

---

### Day 10: Integration Tests for Decomposed System

**Goal:** Verify modules work together

**Tasks:**

1. **Test module interactions**
   ```python
   # hermes/tests/integration/test_decomposed_system.py
   
   @pytest.mark.integration
   def test_message_to_response_flow():
       # MessageHandler → ProviderManager → ToolOrchestrator → Response
       
       loop = ConversationLoop()
       response = loop.run_conversation("What's 2+2?")
       
       assert "4" in response
   
   @pytest.mark.integration
   def test_error_recovery_flow():
       # Error → ErrorHandler → Fallback → Success
       
       loop = ConversationLoop()
       
       # Simulate provider error
       with mock_provider_error("openrouter"):
           response = loop.run_conversation("Test")
       
       # Should use fallback
       assert response is not None
   ```

2. **Test checkpoint/resume with new system**
   ```python
   @pytest.mark.integration
   def test_checkpoint_resume_decomposed():
       loop = ConversationLoop()
       
       # Start task
       task_id = loop.start_task("Long task")
       
       # Checkpoint
       loop.checkpoint_manager.create_checkpoint(task_id, {...})
       
       # Resume
       loop2 = ConversationLoop()
       result = loop2.resume_task(task_id)
       
       assert result is not None
   ```

**Success Criteria:**
- ✅ 20+ integration tests
- ✅ All interactions tested
- ✅ Coverage > 85%
- ✅ All tests pass

**Time:** 6 hours

---

## 📊 Success Metrics

### Test Coverage

**Current:**
- Unit tests: ~5%
- Integration tests: 0%
- E2E tests: 0%
- **Total: ~5%**

**Target:**
- Unit tests: 80%+
- Integration tests: 70%+
- E2E tests: 50%+
- **Total: 80%+**

### Code Quality

**Current:**
- Monolithic modules: 4 (233KB, 95KB, 76KB, 63KB)
- Average module size: 50KB
- Largest method: 3500 lines

**Target:**
- Monolithic modules: 0
- Average module size: 10KB
- Largest method: 200 lines

### Maintainability

**Current:**
- Hard to test
- Hard to understand
- Hard to modify

**Target:**
- Easy to test (80%+ coverage)
- Easy to understand (small, focused modules)
- Easy to modify (clear separation of concerns)

---

## 🎯 Integration with Cleanup Plan

### Parallel Execution

**Week 1 (Cleanup):**
- Day 1: Provider routing fix + Test framework setup
- Day 2: Task queue + Unit tests (model_router, brain_mcp)
- Day 3: Config consolidation + Unit tests (canonical_memory)
- Day 4: Disk cleanup + Integration tests
- Day 5: Dead code removal + E2E tests

**Week 2 (Optimize + Decompose):**
- Day 6-7: Cost tracking + Decompose run_loop.py
- Day 8-9: Memory learning + Test decomposed modules
- Day 10: Monitoring consolidation + Integration tests

### Dependencies

- ✅ Test framework must be ready before decomposition
- ✅ Decomposition must preserve existing functionality
- ✅ All tests must pass before merging

---

## 📋 Checklist

### Week 1: Testing Infrastructure

- [ ] Test framework configured
- [ ] Fixtures created
- [ ] Mocks ready
- [ ] 100+ unit tests written
- [ ] 30+ integration tests written
- [ ] 10+ E2E tests written
- [ ] Coverage > 75%

### Week 2: Decomposition

- [ ] MessageHandler extracted
- [ ] ToolOrchestrator extracted
- [ ] ProviderManager extracted
- [ ] StreamProcessor extracted
- [ ] CheckpointManager extracted
- [ ] ErrorHandler extracted
- [ ] CostTracker extracted
- [ ] ConversationLoop refactored
- [ ] 100+ tests for new modules
- [ ] Coverage > 80%

### Final Verification

- [ ] All tests pass
- [ ] Coverage > 80%
- [ ] No monolithic modules (> 100KB)
- [ ] Average module size < 10KB
- [ ] Largest method < 200 lines
- [ ] Documentation updated

---

## 🚀 Next Steps

1. **Review this plan** with team
2. **Set up test framework** (Day 1)
3. **Start writing tests** (Day 2-5)
4. **Begin decomposition** (Day 6-7)
5. **Test decomposed system** (Day 8-10)

**Status:** READY FOR EXECUTION  
**Priority:** HIGH  
**Timeline:** 2 weeks (parallel with cleanup)  
**Start Date:** 2026-05-06
