# Provider Status

## NVIDIA
- **Status**: Active (primary)
- **Model**: qwen/qwen3-next-80b-a3b-instruct
- **Role**: Default runtime, tool-heavy capable
- **Fallback**: Enabled
- **Cost**: Free

## OpenRouter
- **Status**: disabled_auth_failed
- **Reason**: API key not recognized (HTTP 401)
- **Allowed Models**: None (manual selectable only)

## Omniroute
- **Status**: Disabled (fallback)
- **Reason**: HTTP 402 Payment Required
- **Allowed Models**: None (manual selectable only)

## DeepSeek V4 Flash
- **Status**: unavailable until valid OpenRouter API key is configured
- **Model**: deepseek/deepseek-v4-flash
- **Provider**: OpenRouter
- **Role**: Not usable for any task
- **Cost**: Cheap paid ($0.01-$0.05 per task)
- **Allowed For**: none
- **Disabled For**: code_patch, cheap_surgical_fix, tool_heavy, automatic_fallback, fallback_tool_heavy, monitoring, cron, daily_status
- **Capabilities**:
  - supports_tools: unknown
  - supports_parallel_tool_calls: unknown
  - live_probe_status: route_blocked_auth_failed
  - single_tool_only: unknown
  - allowed_for_tool_heavy: false

## Provider Routing
- **Primary**: NVIDIA
- **Fallback Chain**: Empty
- **Manual Selection**: Enabled for DeepSeek V4 Flash (but unavailable due to auth failure)