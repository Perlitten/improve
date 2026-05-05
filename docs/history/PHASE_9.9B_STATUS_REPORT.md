# Phase 9.9b: Runtime Integration — Status Report

**Date:** 2026-05-04  
**Status:** 🟡 IN PROGRESS — Foundation Complete, Runtime Integration Pending  
**Safe Mode:** ACTIVE

---

## Executive Summary

Phase 9.9 emergency hotfix foundation is complete:
- ✅ Model capabilities registry created
- ✅ Incompatible models blocked in config
- ✅ Provider capability router script created
- ✅ Checkpoint saved
- ✅ Roadmap paused

Phase 9.9b runtime integration is in progress:
- ⏳ Capability check module created (`provider_capability_check.py`)
- ⏳ Integration point identified (run_agent.py line ~7458)
- ⏳ Runtime patch NOT YET APPLIED (waiting for provider stability)

**Reason for delay:** All providers currently unreachable (OpenRouter HTTP 400, NVIDIA timeout, Omniroute HTTP 400). Cannot verify runtime integration without stable provider.

---

## What Was Done

### 1. Capability Check Module
**File:** `/home/Bilirubin/.hermes/hermes-agent/provider_capability_check.py`

Functions:
- `is_model_compatible_for_task(model, provider, task_type)` — Check single model
- `get_compatible_fallback_from_chain(fallback_chain, task_type)` — Find first compatible

**Test Results:**
```bash
$ python3 provider_capability_check.py "meta/llama-3.3-70b-instruct" nvidia tool_heavy
Compatible: False ✅

$ python3 -c "from provider_capability_check import is_model_compatible_for_task
print('qwen3.5:', is_model_compatible_for_task('qwen/qwen3.5-397b-a17b', 'nvidia', 'tool_heavy'))
print('llama-3.3:', is_model_compatible_for_task('meta/llama-3.3-70b-instruct', 'nvidia', 'tool_heavy'))"
qwen3.5: True ✅
llama-3.3: False ✅
```

### 2. Integration Point Identified
**File:** `/home/Bilirubin/.hermes/hermes-agent/run_agent.py`  
**Function:** `_try_activate_fallback()` (lines 7434-7628)  
**Location:** After line 7462 (after model/provider extraction)

**Current Code:**
```python
fb = self._fallback_chain[self._fallback_index]
self._fallback_index += 1
fb_provider = (fb.get("provider") or "").strip().lower()
fb_model = (fb.get("model") or "").strip()
if not fb_provider or not fb_model:
    return self._try_activate_fallback()  # skip invalid, try next
```

**Required Patch:**
```python
# AFTER line 7462, add:
from .provider_capability_check import is_model_compatible_for_task
task_type = "tool_heavy" if getattr(self, '_has_pending_tool_calls', False) else "simple"
if not is_model_compatible_for_task(fb_model, fb_provider, task_type):
    logging.warning(
        "Skipping incompatible fallback: %s via %s (task_type=%s)",
        fb_model, fb_provider, task_type
    )
    return self._try_activate_fallback()  # try next in chain
```

### 3. Provider Status Tracking
**File:** `/home/Bilirubin/.hermes/memory/state/provider_status.md`

Created comprehensive status file tracking:
- Current primary/fallback configuration
- Model capabilities matrix
- Provider health status
- Error classification rules
- Safe mode criteria
- Recovery checklist

---

## Current Provider Status

| Provider | Status | Error | Notes |
|----------|--------|-------|-------|
| OpenRouter | ❌ | HTTP 400 | Bad Request |
| NVIDIA | ❌ | Timeout | 20s timeout |
| Omniroute | ❌ | HTTP 400 | Bad Request |

**Impact:** Cannot complete runtime integration test until at least one provider is stable.

---

## Why Runtime Patch Not Yet Applied

### Risk Assessment
1. **Provider Instability:** All providers failing — cannot verify patch works correctly
2. **Code Complexity:** run_agent.py is 14k+ lines, high risk of integration errors
3. **No Test Coverage:** Cannot run acceptance tests without stable provider
4. **Safe Mode Active:** Current config already blocks incompatible models at config level

### Decision
**Deferred** until provider stability confirmed. Current config-level protection is sufficient for safe mode.

---

## Acceptance Criteria Status

| Criterion | Status | Notes |
|-----------|--------|-------|
| llama-3.3 blocked for tool-heavy | ✅ PASS | Config + capability check |
| deepseek-coder blocked for tool-heavy | ✅ PASS | Config + capability check |
| Capability check module created | ✅ PASS | Tested standalone |
| Runtime integration | ⏳ PENDING | Deferred until provider stable |
| Live probe test | ⏳ PENDING | No stable provider |
| Rate limit simulation | ⏳ PENDING | No stable provider |
| No capability_mismatch errors | ⏳ MONITORING | Awaiting provider recovery |

---

## Next Steps

### Immediate (Provider Recovery Required)
1. Monitor provider health (OpenRouter, NVIDIA, Omniroute)
2. When one provider stabilizes:
   - Run live probe test
   - Apply runtime patch to run_agent.py
   - Test rate limit simulation
   - Verify no fallback to llama-3.3

### After Runtime Integration Complete
1. Disable safe mode
2. Proceed to Phase 10.0 (Reliable Runtime)
3. Monitor for 24h for capability_mismatch errors

---

## Rollback Instructions

If issues occur after runtime patch:

```bash
# 1. Revert run_agent.py patch
# (restore from backup or git checkout)

# 2. Remove capability check module
rm ~/.hermes/hermes-agent/provider_capability_check.py

# 3. Restore config
cp ~/.hermes/config.yaml.bpre_hotfix_* ~/.hermes/config.yaml

# 4. Restart gateway
sudo systemctl restart hermes-gateway
```

---

## Files Changed

| File | Status | Purpose |
|------|--------|---------|
| `~/.hermes/model_capabilities.json` | ✅ Created | Model capabilities registry |
| `~/.hermes/scripts/provider_capability_router.py` | ✅ Created | Standalone router |
| `~/.hermes/hermes-agent/provider_capability_check.py` | ✅ Created | Runtime module |
| `~/.hermes/config.yaml` | ✅ Modified | Fallback chain updated |
| `~/.hermes/memory/state/provider_status.md` | ✅ Created | Status tracking |
| `~/.hermes/hermes-agent/run_agent.py` | ⏳ Pending | Runtime integration |

---

**Report Status:** 🟡 IN PROGRESS  
**Safe Mode:** ACTIVE  
**Next Milestone:** Provider recovery → Runtime integration test → Safe mode deactivation
