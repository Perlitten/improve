# Provider Router Hotfix — Final Report

**Date:** 2026-05-04  
**Status:** ✅ Foundation Complete  
**Safe Mode:** 🟡 ACTIVE  
**Phase 10.0:** ⏸️ ON HOLD  

---

## Status

**Label:** `incident hotfix / provider router foundation complete`

**Summary:** Provider capability router implemented and tested. Model capabilities registry created. Incompatible models blocked. Runtime integration pending provider stability.

---

## Context

Hermes experienced a runtime incident:
1. Primary model (`claude-sonnet-4.5`) hit rate limit
2. Fallback selected: `meta/llama-3.3-70b-instruct` via NVIDIA
3. Fallback failed with HTTP 400: "This model only supports single tool-calls at once"
4. Root cause: Fallback selected without capability check
5. Impact: Task failure, repeated crashes on retry

This was a **capability mismatch**, not a provider outage.

---

## Diagnosis

### What Failed
- Fallback selection logic in `run_agent.py` did not check model capabilities
- `meta/llama-3.3-70b-instruct` does not support parallel tool calls
- HTTP 400 error was treated as retryable, causing infinite loop

### Root Cause
No capability registry or router existed to validate model compatibility before fallback.

---

## Changes Made

### 1. Model Capability Registry ✅
**File:** `/home/Bilirubin/.hermes/model_capabilities.json`

Registry with 6 models:
| Model | Provider | Tools | Parallel | Single Only | Status |
|-------|----------|-------|----------|-------------|--------|
| qwen/qwen3.5-397b | nvidia | ✅ | ✅ | ❌ | assumed_compatible |
| moonshotai/kimi-k2.6 | openrouter | ✅ | ✅ | ❌ | assumed_compatible |
| meta/llama-3.3-70b | nvidia | ✅ | ❌ | ✅ | known_single_tool_only |
| deepseek-coder-6.7b | nvidia | unverified | unverified | unknown | needs_probe |
| llama-3.1-nemotron-70b | nvidia | ✅ | ❌ | ✅ | assumed_single_tool |
| ollama/local | local | ❌ | ❌ | ✅ | not_configured |

### 2. Provider Capability Router ✅
**File:** `/home/Bilirubin/.hermes/scripts/provider_capability_router.py`

Functions:
- `classify_task_requirements()` — Classifies task needs
- `select_model()` — Selects cheapest compatible model
- `fallback_on_error()` — Handles errors with capability awareness
- `is_model_compatible()` — Checks model compatibility

### 3. Routing Policy ✅
**File:** `/home/Bilirubin/.hermes/provider_routing_policy.yaml`

Policy defines:
- Model roles (primary, secondary, code_patch, simple_chat)
- Fallback policies (rate_limit, capability_mismatch, auth_error, timeout)
- Cost policy (prefer free/low, avoid paid for simple tasks)
- Safe mode conditions

---

## Runtime Integration Status

### Current State
- ✅ Capability check module created (`provider_capability_check.py` in Phase 9.9b)
- ✅ Router script created and tested
- ⏳ Runtime patch to `run_agent.py` **deferred** pending provider stability

### Why Deferred
All providers currently unreachable:
- OpenRouter: HTTP 400
- NVIDIA: Timeout (20s)
- Omniroute: HTTP 400

Cannot safely test runtime patch without stable provider. Config-level protection is sufficient for safe mode.

### Integration Point (Identified)
**File:** `~/.hermes/hermes-agent/run_agent.py`  
**Function:** `_try_activate_fallback()` (line ~7458)

Patch required to call `provider_capability_router.select_model()` before activating fallback.

---

## Verification Tests

### Test 1: Select Model for Tool-Heavy Task
```bash
$ python3 provider_capability_router.py select tool_heavy
{
 "action": "select_model",
 "selected_model": "qwen/qwen3.5-397b-a17b",
 "provider": "nvidia",
 "cost_tier": "free_or_low",
 "supports_parallel": true,
 "reason": "Cheapest compatible model for tool_heavy"
}
```
✅ **PASS** — Selected compatible model (qwen3.5)

### Test 2: Check Incompatible Model
```bash
$ python3 provider_capability_router.py check "meta/llama-3.3-70b-instruct" tool_heavy
Model: meta/llama-3.3-70b-instruct
Task: tool_heavy
Compatible: False
```
✅ **PASS** — llama-3.3 correctly blocked for tool_heavy

### Test 3: Fallback on Capability Mismatch
```bash
$ python3 provider_capability_router.py fallback "HTTP 400: only supports single tool-calls" "meta/llama-3.3-70b-instruct" tool_heavy
{
 "error_class": "capability_mismatch",
 "action": "try_next_compatible_model",
 "retry_same_payload": false,
 "mark_model_incompatible": true,
 "incompatible_for_task": "tool_heavy"
}
```
✅ **PASS** — Correctly identifies capability mismatch, does not retry same payload

### Test 4: Registry Validation
```bash
$ python3 -c "import json; r=json.load(open('/home/Bilirubin/.hermes/model_capabilities.json')); print('Models:', len(r['models'])); print('Blocked:', [m for m,c in r['models'].items() if 'tool_heavy' in c.get('disabled_for', [])])"
Models: 6
Blocked: ['meta/llama-3.3-70b-instruct', 'deepseek-ai/deepseek-coder-6.7b-instruct', 'nvidia/llama-3.1-nemotron-70b-instruct', 'ollama/local']
```
✅ **PASS** — 4 models blocked for tool_heavy tasks

---

## Provider Status

| Provider | Status | Last Error | Notes |
|----------|--------|------------|-------|
| OpenRouter | ❌ | HTTP 400 | Bad Request |
| NVIDIA | ❌ | Timeout | 20s timeout |
| Omniroute | ❌ | HTTP 400 | Bad Request |

**Allowed Models (assumed compatible):**
- `qwen/qwen3.5-397b-a17b` (nvidia)
- `moonshotai/kimi-k2.6` (openrouter)

**Blocked Models (tool_heavy):**
- `meta/llama-3.3-70b-instruct` (single_tool_only)
- `deepseek-ai/deepseek-coder-6.7b-instruct` (unverified)
- `nvidia/llama-3.1-nemotron-70b-instruct` (single_tool_only)
- `ollama/local` (no tool support)

---

## Safe Mode

### Status: ACTIVE 🟡

**Conditions for Deactivation:**
1. ✅ Provider router created and tested
2. ⏳ Runtime integration complete (deferred)
3. ⏳ Live probe passed (no stable provider)
4. ⏳ No capability_mismatch errors in 24h logs
5. ⏳ Checkpoint + pause verified

**Allowed During Safe Mode:**
- Health checks
- Backup checks
- Disk cleanup (dry-run)
- Provider probe
- Router tests
- Logs review

**Forbidden During Safe Mode:**
- Phase 10.0 Reliable Runtime
- Long-running roadmap execution
- Multi-tool-heavy tasks
- Source ingestion
- n8n automation

---

## Risks

### Remaining Limitations
1. **Runtime Integration Pending:** Router not yet integrated into `run_agent.py` fallback path
2. **Provider Instability:** All providers currently unreachable
3. **Untested Fallback:** Cannot verify fallback chain works without stable provider
4. **Assumed Capabilities:** Model capabilities based on documentation, not live probe

### Mitigation
- Config-level protection blocks incompatible models
- Router tested standalone
- Safe mode prevents risky operations
- Checkpoint mechanism ready

---

## Rollback

If issues occur:

```bash
# 1. Restore config
cp ~/.hermes/config.yaml.bpre_hotfix_* ~/.hermes/config.yaml

# 2. Remove router
rm ~/.hermes/scripts/provider_capability_router.py

# 3. Remove registry
rm ~/.hermes/model_capabilities.json

# 4. Remove policy
rm ~/.hermes/provider_routing_policy.yaml

# 5. Restart gateway
sudo systemctl restart hermes-gateway
```

---

## Next Steps

### Immediate (Provider Recovery Required)
1. Monitor provider health (OpenRouter, NVIDIA, Omniroute)
2. When one provider stabilizes:
   - Apply runtime patch to `run_agent.py`
   - Run live model bakeoff
   - Test rate limit simulation
   - Verify fallback chain

### After Runtime Integration Complete
1. Disable safe mode
2. Proceed to Phase 10.0 (Reliable Runtime)
3. Monitor for 24h for capability_mismatch errors

---

## Acceptance Criteria Status

| Criterion | Status | Notes |
|-----------|--------|-------|
| Registry exists | ✅ PASS | `/home/Bilirubin/.hermes/model_capabilities.json` |
| Router exists | ✅ PASS | `/home/Bilirubin/.hermes/scripts/provider_capability_router.py` |
| Policy exists | ✅ PASS | `/home/Bilirubin/.hermes/provider_routing_policy.yaml` |
| llama-3.3 rejected for tool_heavy | ✅ PASS | Tested via CLI |
| deepseek rejected for tool_heavy | ✅ PASS | Listed in disabled_for |
| qwen allowed (assumed) | ✅ PASS | Selected as primary |
| Simulated rate limit | ⏳ PENDING | Requires stable provider |
| Capability mismatch handling | ✅ PASS | Router returns correct action |
| Runtime integration | ⏳ PENDING | Deferred pending provider stability |
| No secrets printed | ✅ PASS | Verified |
| operator_standard_eval | ⏳ PENDING | Will run after integration |
| audit/hygiene/secret-scan | ⏳ TODO | Pending |

---

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `~/.hermes/model_capabilities.json` | Created | Model capabilities registry |
| `~/.hermes/scripts/provider_capability_router.py` | Created | Router script |
| `~/.hermes/provider_routing_policy.yaml` | Created | Routing policy |
| `~/.hermes/config.yaml` | Modified (Phase 9.9) | Fallback chain |
| `~/.hermes/hermes-agent/provider_capability_check.py` | Created (Phase 9.9b) | Runtime module |
| `~/.hermes/memory/state/provider_status.md` | Created (Phase 9.9b) | Status tracking |

---

## Conclusion

**Phase 9.9 Provider Router Foundation: COMPLETE** ✅

- Model capabilities registry created
- Provider capability router implemented and tested
- Incompatible models blocked (llama-3.3, deepseek-coder, nemotron-70b)
- Compatible fallback chain configured (qwen3.5 → kimi-k2.6)
- Error classification implemented (capability_mismatch, rate_limit, auth_error, timeout)
- Checkpoint + pause mechanism ready

**Phase 9.9b Runtime Integration: PENDING** ⏳

- Runtime patch deferred pending provider stability
- Integration point identified (`run_agent.py` line ~7458)
- Safe mode remains active

**Phase 10.0 Reliable Runtime: ON HOLD** ⏸️

- Will proceed only after provider stability confirmed
- Requires successful live probe and runtime integration test

---

**Report Status:** ✅ Foundation Complete  
**Safe Mode:** 🟡 ACTIVE  
**Next Milestone:** Provider recovery → Runtime integration → Safe mode deactivation
