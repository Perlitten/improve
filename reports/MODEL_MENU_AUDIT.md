# Status
foundation complete

# Scope
Phase A (read-only): audit источников `/model` menu, источников списков моделей, маршрутизации provider/model и fallback.

# Evidence gathered
- `grep -RniE "Model Configuration|Select a provider|Select a model|/model|available_models|model list|models.py|openrouter|nvidia|omniroute|deepseek|qwen|kimi|claude" /home/Bilirubin/.hermes /srv/automation`
- `read_file`:
  - `/home/Bilirubin/.hermes/hermes-agent/hermes_cli/models.py`
  - `/home/Bilirubin/.hermes/hermes-agent/hermes_cli/model_switch.py`
  - `/home/Bilirubin/.hermes/hermes-agent/hermes_cli/providers.py`
  - `/home/Bilirubin/.hermes/hermes-agent/hermes_cli/model_catalog.py`
  - `/home/Bilirubin/.hermes/hermes-agent/hermes_cli/model_registry.py`
  - `/home/Bilirubin/.hermes/hermes-agent/gateway/run.py`
  - `/home/Bilirubin/.hermes/hermes-agent/gateway/platforms/telegram.py`
  - `/home/Bilirubin/.hermes/hermes-agent/cli.py`
  - `/home/Bilirubin/.hermes/hermes-agent/run_agent.py`

# Findings (requested 10 items)

## 1) Where provider list comes from
Primary source for `/model` UI list:
- `hermes_cli/model_switch.py::list_authenticated_providers()`
- It composes providers from:
  - `PROVIDER_TO_MODELS_DEV` (models.dev mapping)
  - `HERMES_OVERLAYS` (Hermes-specific providers)
  - `CANONICAL_PROVIDERS`
  - user config (`providers`, `custom_providers`)
- Used by:
  - CLI `/model` picker in `cli.py`
  - Gateway `/model` in `gateway/run.py`
  - Telegram picker in `gateway/platforms/telegram.py`

## 2) Where NVIDIA model list comes from
Two paths:
- Static curated fallback: `_PROVIDER_MODELS["nvidia"]` in `hermes_cli/models.py`
- Dynamic merged path: `provider_model_ids("nvidia")` -> for providers in `_MODELS_DEV_PREFERRED` it calls `_merge_with_models_dev(...)`, adding models.dev entries.

## 3) Where OpenRouter model list comes from
`hermes_cli/models.py::fetch_openrouter_models()`:
- Base curated list = remote manifest (`model_catalog.get_curated_openrouter_models()`) or local `OPENROUTER_MODELS` fallback.
- Then it calls live OpenRouter `/api/v1/models`, but **filters only curated IDs** (`preferred_ids`) and excludes entries failing tool-support heuristic.
- Result is cached in `_openrouter_catalog_cache`.

## 4) Hardcoded vs config vs cached vs dynamic
Hybrid:
- Hardcoded: `_PROVIDER_MODELS`, `OPENROUTER_MODELS`, aliases, labels.
- Remote config-like: `model_catalog` manifest (`website/static/api/model-catalog.json`) cached to `~/.hermes/cache/model_catalog.json`.
- Dynamic discovery: models.dev merge for preferred providers; some providers use live `/models` probes.
- In-process caches: `_openrouter_catalog_cache`, `_ai_gateway_catalog_cache`, config caches.

## 5) Why OpenRouter only shows ~35
Because OpenRouter menu is curated-first by design:
- `fetch_openrouter_models()` intersects live `/models` with curated `preferred_ids`.
- Non-curated live OpenRouter models are not shown in picker even if available.
So menu count follows curated snapshot, not full provider inventory.

## 6) Why NVIDIA shows many but some fail
Because model visibility != runtime capability/availability proof:
- models.dev merge can surface many IDs.
- `/model` listing does not require successful capability probe per model.
- Runtime can still fail due parameter mismatch, tool-call limitations, provider-side availability, or payload incompatibility.

## 7) Which files control menu labels
- Provider labels: `hermes_cli/models.py` (`_PROVIDER_LABELS`) + `hermes_cli/providers.py::get_label()`.
- Telegram picker text/layout: `gateway/platforms/telegram.py` (`send_model_picker`, `_handle_model_picker_callback`).
- CLI picker rendering: `cli.py` (`_open_model_picker`, `/model` handlers).

## 8) Which files control provider/model_id mapping
- `hermes_cli/model_switch.py` (`switch_model`, alias resolution, provider resolution, parsing).
- `hermes_cli/models.py` (`_PROVIDER_MODELS`, `_PROVIDER_ALIASES`, `provider_model_ids`, detect logic).
- `hermes_cli/providers.py` (canonical provider identity + alias layer + overlays).
- `hermes_cli/model_normalize.py` (provider-specific model normalization).

## 9) Which files control current/default model
- Runtime read/write from `~/.hermes/config.yaml` keys:
  - `model.provider`
  - `model.default`
- Written by:
  - CLI `/model --global` in `cli.py` (via `save_config_value`)
  - Gateway `/model --global` in `gateway/run.py`
- Session overrides live in gateway memory (`_session_model_overrides`) and CLI state.

## 10) Which files control fallback
- Core fallback engine: `run_agent.py::_try_activate_fallback()`
- Fallback chain source: `fallback_model` config -> `_fallback_chain`
- Compatibility guard: `provider_capability_check.is_model_compatible_for_task(...)` called before activating fallback.
- `hermes_cli/model_registry.py` contains strict policy helpers (`disabled_providers`, `is_fallback_allowed`) but currently this module is not a central enforcement point for main runtime fallback path.

# Root causes summary
1. OpenRouter menu is intentionally curated/intersection-based, not full discovery-based.
2. NVIDIA menu can include unproven models (models.dev merged) without mandatory probe gate.
3. Fallback policy enforcement is split; strict registry exists but is not the single runtime gate everywhere.

# Security
- secrets printed: no
- API keys shown: no

# Report artifact
- `/home/Bilirubin/workspace/reports/MODEL_MENU_AUDIT.md`

# Next step
Phase B/C: implement local model catalog cache + probe results + safe probing script, then wire `/model` visibility/selection to `status/selectable/manual_only/fallback_allowed`.
