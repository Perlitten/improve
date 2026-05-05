# Phase 9.9: Provider Capability Hotfix — Implementation Report

## Status
**COMPLETE** ✅

## Context
Emergency hotfix required after repeated HTTP 400 errors when fallback model `meta/llama-3.3-70b-instruct` (NVIDIA) rejected multi-tool payloads with "This model only supports single tool-calls at once".

## Diagnosis
- **Root Cause:** Fallback model selection was capability-blind
- **Trigger:** Primary model rate limit → fallback to incompatible model → HTTP 400
- **Impact:** Repeated failures, task interruption, roadmap delay

## Execution

### Files Created
1. `/home/Bilirubin/.hermes/model_capabilities.json` — Model capabilities registry
2. `/home/Bilirubin/.hermes/scripts/provider_capability_router.py` — Capability-aware router
3. `/home/Bilirubin/.hermes/state/checkpoints/hotfix_provider_capability_20260504.md` — Checkpoint doc

### Files Modified
1. `/home/Bilirubin/.hermes/config.yaml` — Updated fallback_model config
2. Backup created: `~/.hermes/config.yaml.bpre_hotfix_<timestamp>`

### Config Changes
```yaml
# Before
fallback_model:
  model: meta/llama-3.3-70b-instruct
  provider: nvidia

# After
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

## Verification

### Test 1: Incompatible Model Check
```bash
$ python3 provider_capability_router.py --check-model "meta/llama-3.3-70b-instruct" --task-type tool_heavy
# Result: Compatible: False ✅
```

### Test 2: Fallback Selection
```bash
$ python3 provider_capability_router.py --simulate-rate-limit --task-type tool_heavy
# Result: SUCCESS: Fallback to kr/claude-sonnet-4.5 ✅
```

### Test 3: Config Validation
```bash
$ grep -A 12 "fallback_model:" ~/.hermes/config.yaml
# Result: Shows updated chain and blocked models ✅
```

## Current State
- **Provider Health:** All providers currently unavailable (OpenRouter timeout, NVIDIA timeout, Omniroute 400)
- **Safe Mode:** Active
- **Active Tasks:** None (paused pending provider recovery)
- **Phase 10.0:** On hold until stability confirmed

## Risks
- All providers currently unreachable — cannot fully test hotfix until recovery
- Fallback chain relies on omniroute stability
- No real-world rate limit test yet

## Rollback
```bash
cp ~/.hermes/config.yaml.bpre_hotfix_* ~/.hermes/config.yaml
rm ~/.hermes/scripts/provider_capability_router.py
rm ~/.hermes/model_capabilities.json
```

## Next Step
Wait for provider recovery, then:
1. Verify no HTTP 400 errors
2. Test with actual rate limit scenario
3. If stable → proceed to Phase 10.0

---
**Report Generated:** 2026-05-04  
**Operator:** Hermes Agent  
**Compliance:** Hermes Senior Operator Standard
