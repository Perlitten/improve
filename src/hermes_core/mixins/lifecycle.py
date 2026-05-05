import logging
import json
import asyncio
import time
import uuid
import httpx
import threading
import sys
import os
from typing import Any, Optional, Dict, List, Tuple
logger = logging.getLogger(__name__)

class LifecycleMixin:
    def switch_model(self, new_model, new_provider, api_key='', base_url='', api_mode=''):
            """Switch the model/provider in-place for a live agent.

            Called by the /model command handlers (CLI and gateway) after
            ``model_switch.switch_model()`` has resolved credentials and
            validated the model.  This method performs the actual runtime
            swap: rebuilding clients, updating caching flags, and refreshing
            the context compressor.

            The implementation mirrors ``_try_activate_fallback()`` for the
            client-swap logic but also updates ``_primary_runtime`` so the
            change persists across turns (unlike fallback which is
            turn-scoped).
            """
            from hermes_cli.providers import determine_api_mode

            # ── Determine api_mode if not provided ──
            if not api_mode:
                api_mode = determine_api_mode(new_provider, base_url)

            # Defense-in-depth: ensure OpenCode base_url doesn't carry a trailing
            # /v1 into the anthropic_messages client, which would cause the SDK to
            # hit /v1/v1/messages.  `model_switch.switch_model()` already strips
            # this, but we guard here so any direct callers (future code paths,
            # tests) can't reintroduce the double-/v1 404 bug.
            if (
                api_mode == "anthropic_messages"
                and new_provider in ("opencode-zen", "opencode-go")
                and isinstance(base_url, str)
                and base_url
            ):
                base_url = re.sub(r"/v1/?$", "", base_url)

            old_model = self.model
            old_provider = self.provider

            # ── Swap core runtime fields ──
            self.model = new_model
            self.provider = new_provider
            self.base_url = base_url or self.base_url
            self.api_mode = api_mode
            # Invalidate transport cache — new api_mode may need a different transport
            if hasattr(self, "_transport_cache"):
                self._transport_cache.clear()
            if api_key:
                self.api_key = api_key

            # ── Build new client ──
            if api_mode == "anthropic_messages":
                from agent.anthropic_adapter import (
                    build_anthropic_client,
                    resolve_anthropic_token,
                    _is_oauth_token,
                )
                # Only fall back to ANTHROPIC_TOKEN when the provider is actually Anthropic.
                # Other anthropic_messages providers (MiniMax, Alibaba, etc.) must use their own
                # API key — falling back would send Anthropic credentials to third-party endpoints.
                _is_native_anthropic = new_provider == "anthropic"
                effective_key = (api_key or self.api_key or resolve_anthropic_token() or "") if _is_native_anthropic else (api_key or self.api_key or "")
                self.api_key = effective_key
                self._anthropic_api_key = effective_key
                self._anthropic_base_url = base_url or getattr(self, "_anthropic_base_url", None)
                self._anthropic_client = build_anthropic_client(
                    effective_key, self._anthropic_base_url,
                    timeout=get_provider_request_timeout(self.provider, self.model),
                )
                self._is_anthropic_oauth = _is_oauth_token(effective_key) if _is_native_anthropic else False
                self.client = None
                self._client_kwargs = {}
            else:
                effective_key = api_key or self.api_key
                effective_base = base_url or self.base_url
                self._client_kwargs = {
                    "api_key": effective_key,
                    "base_url": effective_base,
                }
                _sm_timeout = get_provider_request_timeout(self.provider, self.model)
                if _sm_timeout is not None:
                    self._client_kwargs["timeout"] = _sm_timeout
                self.client = self._create_openai_client(
                    dict(self._client_kwargs),
                    reason="switch_model",
                    shared=True,
                )

            # ── Re-evaluate prompt caching ──
            self._use_prompt_caching, self._use_native_cache_layout = (
                self._anthropic_prompt_cache_policy(
                    provider=new_provider,
                    base_url=self.base_url,
                    api_mode=api_mode,
                    model=new_model,
                )
            )

            # ── LM Studio: preload before probing context length ──
            self._ensure_lmstudio_runtime_loaded()

            # ── Update context compressor ──
            if hasattr(self, "context_compressor") and self.context_compressor:
                from agent.model_metadata import get_model_context_length
                # Re-read custom_providers from live config so per-model
                # context_length overrides are honored when switching to a
                # custom provider mid-session (closes #15779).
                _sm_custom_providers = None
                try:
                    from hermes_cli.config import load_config, get_compatible_custom_providers
                    _sm_cfg = load_config()
                    _sm_custom_providers = get_compatible_custom_providers(_sm_cfg)
                except Exception:
                    _sm_custom_providers = None
                new_context_length = get_model_context_length(
                    self.model,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    provider=self.provider,
                    config_context_length=getattr(self, "_config_context_length", None),
                    custom_providers=_sm_custom_providers,
                )
                self.context_compressor.update_model(
                    model=self.model,
                    context_length=new_context_length,
                    base_url=self.base_url,
                    api_key=getattr(self, "api_key", ""),
                    provider=self.provider,
                    api_mode=self.api_mode,
                )

            # ── Invalidate cached system prompt so it rebuilds next turn ──
            self._cached_system_prompt = None

            # ── Update _primary_runtime so the change persists across turns ──
            _cc = self.context_compressor if hasattr(self, "context_compressor") and self.context_compressor else None
            self._primary_runtime = {
                "model": self.model,
                "provider": self.provider,
                "base_url": self.base_url,
                "api_mode": self.api_mode,
                "api_key": getattr(self, "api_key", ""),
                "client_kwargs": dict(self._client_kwargs),
                "use_prompt_caching": self._use_prompt_caching,
                "use_native_cache_layout": self._use_native_cache_layout,
                "compressor_model": getattr(_cc, "model", self.model) if _cc else self.model,
                "compressor_base_url": getattr(_cc, "base_url", self.base_url) if _cc else self.base_url,
                "compressor_api_key": getattr(_cc, "api_key", "") if _cc else "",
                "compressor_provider": getattr(_cc, "provider", self.provider) if _cc else self.provider,
                "compressor_context_length": _cc.context_length if _cc else 0,
                "compressor_threshold_tokens": _cc.threshold_tokens if _cc else 0,
            }
            if api_mode == "anthropic_messages":
                self._primary_runtime.update({
                    "anthropic_api_key": self._anthropic_api_key,
                    "anthropic_base_url": self._anthropic_base_url,
                    "is_anthropic_oauth": self._is_anthropic_oauth,
                })

            # ── Reset fallback state ──
            self._fallback_activated = False
            self._fallback_index = 0

            # When the user deliberately swaps primary providers (e.g. openrouter
            # → anthropic), drop any fallback entries that target the OLD primary
            # or the NEW one.  The chain was seeded from config at agent init for
            # the original provider — without pruning, a failed turn on the new
            # primary silently re-activates the provider the user just rejected,
            # which is exactly what was reported during TUI v2 blitz testing
            # ("switched to anthropic, tui keeps trying openrouter").
            old_norm = (old_provider or "").strip().lower()
            new_norm = (new_provider or "").strip().lower()
            fallback_chain = list(getattr(self, "_fallback_chain", []) or [])
            if old_norm and new_norm and old_norm != new_norm:
                fallback_chain = [
                    entry for entry in fallback_chain
                    if (entry.get("provider") or "").strip().lower() not in {old_norm, new_norm}
                ]
            self._fallback_chain = fallback_chain
            self._fallback_model = fallback_chain[0] if fallback_chain else None

            logging.info(
                "Model switched in-place: %s (%s) -> %s (%s)",
                old_model, old_provider, new_model, new_provider,
            )


    def interrupt(self, message: str = None) -> None:
            """
            Request the agent to interrupt its current tool-calling loop.

            Call this from another thread (e.g., input handler, message receiver)
            to gracefully stop the agent and process a new message.

            Also signals long-running tool executions (e.g. terminal commands)
            to terminate early, so the agent can respond immediately.

            Args:
                message: Optional new message that triggered the interrupt.
                         If provided, the agent will include this in its response context.

            Example (CLI):
                # In a separate input thread:
                if user_typed_something:
                    agent.interrupt(user_input)

            Example (Messaging):
                # When new message arrives for active session:
                if session_has_running_agent:
                    running_agent.interrupt(new_message.text)
            """
            self._interrupt_requested = True
            self._interrupt_message = message
            # Signal all tools to abort any in-flight operations immediately.
            # Scope the interrupt to this agent's execution thread so other
            # agents running in the same process (gateway) are not affected.
            if self._execution_thread_id is not None:
                _set_interrupt(True, self._execution_thread_id)
                self._interrupt_thread_signal_pending = False
            else:
                # The interrupt arrived before run_conversation() finished
                # binding the agent to its execution thread. Defer the tool-level
                # interrupt signal until startup completes instead of targeting
                # the caller thread by mistake.
                self._interrupt_thread_signal_pending = True
            # Fan out to concurrent-tool worker threads.  Those workers run tools
            # on their own tids (ThreadPoolExecutor workers), so `is_interrupted()`
            # inside a tool only sees an interrupt when their specific tid is in
            # the `_interrupted_threads` set.  Without this propagation, an
            # already-running concurrent tool (e.g. a terminal command hung on
            # network I/O) never notices the interrupt and has to run to its own
            # timeout.  See `_run_tool` for the matching entry/exit bookkeeping.
            # `getattr` fallback covers test stubs that build AIAgent via
            # object.__new__ and skip __init__.
            _tracker = getattr(self, "_tool_worker_threads", None)
            _tracker_lock = getattr(self, "_tool_worker_threads_lock", None)
            if _tracker is not None and _tracker_lock is not None:
                with _tracker_lock:
                    _worker_tids = list(_tracker)
                for _wtid in _worker_tids:
                    try:
                        _set_interrupt(True, _wtid)
                    except Exception:
                        pass
            # Propagate interrupt to any running child agents (subagent delegation)
            with self._active_children_lock:
                children_copy = list(self._active_children)
            for child in children_copy:
                try:
                    child.interrupt(message)
                except Exception as e:
                    logger.debug("Failed to propagate interrupt to child agent: %s", e)
            if not self.quiet_mode:
                print("\n⚡ Interrupt requested" + (f": '{message[:40]}...'" if message and len(message) > 40 else f": '{message}'" if message else ""))


    def clear_interrupt(self) -> None:
            """Clear any pending interrupt request and the per-thread tool interrupt signal."""
            self._interrupt_requested = False
            self._interrupt_message = None
            self._interrupt_thread_signal_pending = False
            if self._execution_thread_id is not None:
                _set_interrupt(False, self._execution_thread_id)
            # Also clear any concurrent-tool worker thread bits.  Tracked
            # workers normally clear their own bit on exit, but an explicit
            # clear here guarantees no stale interrupt can survive a turn
            # boundary and fire on a subsequent, unrelated tool call that
            # happens to get scheduled onto the same recycled worker tid.
            # `getattr` fallback covers test stubs that build AIAgent via
            # object.__new__ and skip __init__.
            _tracker = getattr(self, "_tool_worker_threads", None)
            _tracker_lock = getattr(self, "_tool_worker_threads_lock", None)
            if _tracker is not None and _tracker_lock is not None:
                with _tracker_lock:
                    _worker_tids = list(_tracker)
                for _wtid in _worker_tids:
                    try:
                        _set_interrupt(False, _wtid)
                    except Exception:
                        pass
            # A hard interrupt supersedes any pending /steer — the steer was
            # meant for the agent's next tool-call iteration, which will no
            # longer happen. Drop it instead of surprising the user with a
            # late injection on the post-interrupt turn.
            _steer_lock = getattr(self, "_pending_steer_lock", None)
            if _steer_lock is not None:
                with _steer_lock:
                    self._pending_steer = None


    def is_interrupted(self) -> bool:
            """Check if an interrupt has been requested."""
            return self._interrupt_requested


    def steer(self, text: str) -> bool:
            """
            Inject a user message into the next tool result without interrupting.

            Unlike interrupt(), this does NOT stop the current tool call. The
            text is stashed and the agent loop appends it to the LAST tool
            result's content once the current tool batch finishes. The model
            sees the steer as part of the tool output on its next iteration.

            Thread-safe: callable from gateway/CLI/TUI threads. Multiple calls
            before the drain point concatenate with newlines.

            Args:
                text: The user text to inject. Empty strings are ignored.

            Returns:
                True if the steer was accepted, False if the text was empty.
            """
            if not text or not text.strip():
                return False
            cleaned = text.strip()
            _lock = getattr(self, "_pending_steer_lock", None)
            if _lock is None:
                # Test stubs that built AIAgent via object.__new__ skip __init__.
                # Fall back to direct attribute set; no concurrent callers expected
                # in those stubs.
                existing = getattr(self, "_pending_steer", None)
                self._pending_steer = (existing + "\n" + cleaned) if existing else cleaned
                return True
            with _lock:
                if self._pending_steer:
                    self._pending_steer = self._pending_steer + "\n" + cleaned
                else:
                    self._pending_steer = cleaned
            return True


    def _drain_pending_steer(self) -> Optional[str]:
            """Return the pending steer text (if any) and clear the slot.

            Safe to call from the agent execution thread after appending tool
            results. Returns None when no steer is pending.
            """
            _lock = getattr(self, "_pending_steer_lock", None)
            if _lock is None:
                text = getattr(self, "_pending_steer", None)
                self._pending_steer = None
                return text
            with _lock:
                text = self._pending_steer
                self._pending_steer = None
            return text


    def _apply_pending_steer_to_tool_results(self, messages: list, num_tool_msgs: int) -> None:
            """Append any pending /steer text to the last tool result in this turn.

            Called at the end of a tool-call batch, before the next API call.
            The steer is appended to the last ``role:"tool"`` message's content
            with a clear marker so the model understands it came from the user
            and NOT from the tool itself. Role alternation is preserved —
            nothing new is inserted, we only modify existing content.

            Args:
                messages: The running messages list.
                num_tool_msgs: Number of tool results appended in this batch;
                    used to locate the tail slice safely.
            """
            if num_tool_msgs <= 0 or not messages:
                return
            steer_text = self._drain_pending_steer()
            if not steer_text:
                return
            # Find the last tool-role message in the recent tail. Skipping
            # non-tool messages defends against future code appending
            # something else at the boundary.
            target_idx = None
            for j in range(len(messages) - 1, max(len(messages) - num_tool_msgs - 1, -1), -1):
                msg = messages[j]
                if isinstance(msg, dict) and msg.get("role") == "tool":
                    target_idx = j
                    break
            if target_idx is None:
                # No tool result in this batch (e.g. all skipped by interrupt);
                # put the steer back so the caller's fallback path can deliver
                # it as a normal next-turn user message.
                _lock = getattr(self, "_pending_steer_lock", None)
                if _lock is not None:
                    with _lock:
                        if self._pending_steer:
                            self._pending_steer = self._pending_steer + "\n" + steer_text
                        else:
                            self._pending_steer = steer_text
                else:
                    existing = getattr(self, "_pending_steer", None)
                    self._pending_steer = (existing + "\n" + steer_text) if existing else steer_text
                return
            marker = f"\n\nUser guidance: {steer_text}"
            existing_content = messages[target_idx].get("content", "")
            if not isinstance(existing_content, str):
                # Anthropic multimodal content blocks — preserve them and append
                # a text block at the end.
                try:
                    blocks = list(existing_content) if existing_content else []
                    blocks.append({"type": "text", "text": marker.lstrip()})
                    messages[target_idx]["content"] = blocks
                except Exception:
                    # Fall back to string replacement if content shape is unexpected.
                    messages[target_idx]["content"] = f"{existing_content}{marker}"
            else:
                messages[target_idx]["content"] = existing_content + marker
            logger.info(
                "Delivered /steer to agent after tool batch (%d chars): %s",
                len(steer_text),
                steer_text[:120] + ("..." if len(steer_text) > 120 else ""),
            )


    def reset_session_state(self):
            """Reset all session-scoped token counters to 0 for a fresh session.

            This method encapsulates the reset logic for all session-level metrics
            including:
            - Token usage counters (input, output, total, prompt, completion)
            - Cache read/write tokens
            - API call count
            - Reasoning tokens
            - Estimated cost tracking
            - Context compressor internal counters

            The method safely handles optional attributes (e.g., context compressor)
            using ``hasattr`` checks.

            This keeps the counter reset logic DRY and maintainable in one place
            rather than scattering it across multiple methods.
            """
            # Token usage counters
            self.session_total_tokens = 0
            self.session_input_tokens = 0
            self.session_output_tokens = 0
            self.session_prompt_tokens = 0
            self.session_completion_tokens = 0
            self.session_cache_read_tokens = 0
            self.session_cache_write_tokens = 0
            self.session_reasoning_tokens = 0
            self.session_api_calls = 0
            self.session_estimated_cost_usd = 0.0
            self.session_cost_status = "unknown"
            self.session_cost_source = "none"

            # Turn counter (added after reset_session_state was first written — #2635)
            self._user_turn_count = 0

            # Context engine reset (works for both built-in compressor and plugins)
            if hasattr(self, "context_compressor") and self.context_compressor:
                self.context_compressor.on_session_reset()


    def close(self) -> None:
            """Release all resources held by this agent instance.

            Cleans up subprocess resources that would otherwise become orphans:
            - Background processes tracked in ProcessRegistry
            - Terminal sandbox environments
            - Browser daemon sessions
            - Active child agents (subagent delegation)
            - OpenAI/httpx client connections

            Safe to call multiple times (idempotent).  Each cleanup step is
            independently guarded so a failure in one does not prevent the rest.
            """
            task_id = getattr(self, "session_id", None) or ""

            # 1. Kill background processes for this task
            try:
                from tools.process_registry import process_registry
                process_registry.kill_all(task_id=task_id)
            except Exception:
                pass

            # 2. Clean terminal sandbox environments
            try:
                cleanup_vm(task_id)
            except Exception:
                pass

            # 3. Clean browser daemon sessions
            try:
                cleanup_browser(task_id)
            except Exception:
                pass

            # 4. Close active child agents
            try:
                with self._active_children_lock:
                    children = list(self._active_children)
                    self._active_children.clear()
                for child in children:
                    try:
                        child.close()
                    except Exception:
                        pass
            except Exception:
                pass

            # 5. Close the OpenAI/httpx client
            try:
                client = getattr(self, "client", None)
                if client is not None:
                    self._close_openai_client(client, reason="agent_close", shared=True)
                    self.client = None
            except Exception:
                pass


    def release_clients(self) -> None:
            """Release LLM client resources WITHOUT tearing down session tool state.

            Used by the gateway when evicting this agent from _agent_cache for
            memory-management reasons (LRU cap or idle TTL) — the session may
            resume at any time with a freshly-built AIAgent that reuses the
            same task_id / session_id, so we must NOT kill:
              - process_registry entries for task_id (user's bg shells)
              - terminal sandbox for task_id (cwd, env, shell state)
              - browser daemon for task_id (open tabs, cookies)
              - memory provider (has its own lifecycle; keeps running)

            We DO close:
              - OpenAI/httpx client pool (big chunk of held memory + sockets;
                the rebuilt agent gets a fresh client anyway)
              - Active child subagents (per-turn artefacts; safe to drop)

            Safe to call multiple times.  Distinct from close() — which is the
            hard teardown for actual session boundaries (/new, /reset, session
            expiry).
            """
            # Close active child agents (per-turn; no cross-turn persistence).
            try:
                with self._active_children_lock:
                    children = list(self._active_children)
                    self._active_children.clear()
                for child in children:
                    try:
                        child.release_clients()
                    except Exception:
                        # Fall back to full close on children; they're per-turn.
                        try:
                            child.close()
                        except Exception:
                            pass
            except Exception:
                pass

            # Close the OpenAI/httpx client to release sockets immediately.
            try:
                client = getattr(self, "client", None)
                if client is not None:
                    self._close_openai_client(client, reason="cache_evict", shared=True)
                    self.client = None
            except Exception:
                pass


    def _ensure_lmstudio_runtime_loaded(self, config_context_length: Optional[int] = None) -> None:
            """
            Preload the LM Studio model with at least Hermes' minimum context.
            """
            if (self.provider or "").strip().lower() != "lmstudio":
                return
            try:
                from agent.model_metadata import MINIMUM_CONTEXT_LENGTH
                from hermes_cli.models import ensure_lmstudio_model_loaded
                if config_context_length is None:
                    config_context_length = getattr(self, "_config_context_length", None)
                target_ctx = max(config_context_length or 0, MINIMUM_CONTEXT_LENGTH)
                loaded_ctx = ensure_lmstudio_model_loaded(
                    self.model, self.base_url, getattr(self, "api_key", ""), target_ctx,
                )
                if loaded_ctx:
                    # Push into the live compressor so the status bar reflects the
                    # real loaded ctx the moment the load resolves, instead of
                    # holding the previous model's value (or "ctx --") through the
                    # next render tick.
                    cc = getattr(self, "context_compressor", None)
                    if cc is not None:
                        cc.update_model(
                            model=self.model,
                            context_length=loaded_ctx,
                            base_url=self.base_url,
                            api_key=getattr(self, "api_key", ""),
                            provider=self.provider,
                            api_mode=self.api_mode,
                        )
            except Exception as err:
                logger.debug("LM Studio preload skipped: %s", err)


    def _should_start_quiet_spinner(self) -> bool:
            """Return True when quiet-mode spinner output has a safe sink.

            In headless/stdio-protocol environments, a raw spinner with no custom
            ``_print_fn`` falls back to ``sys.stdout`` and can corrupt protocol
            streams such as ACP JSON-RPC. Allow quiet spinners only when either:
            - output is explicitly rerouted via ``_print_fn``; or
            - stdout is a real TTY.
            """
            if self._print_fn is not None:
                return True
            stream = getattr(sys, "stdout", None)
            if stream is None:
                return False
            try:
                return bool(stream.isatty())
            except (AttributeError, ValueError, OSError):
                return False


    def _should_emit_quiet_tool_messages(self) -> bool:
            """Return True when quiet-mode tool summaries should print directly.

            Quiet mode is used by both the interactive CLI and embedded/library
            callers. The CLI may still want compact progress hints when no callback
            owns rendering. Embedded/library callers, on the other hand, expect
            quiet mode to be truly silent.
            """
            return (
                self.quiet_mode
                and not self.tool_progress_callback
                and getattr(self, "platform", "") == "cli"
            )


    def _current_main_runtime(self) -> Dict[str, str]:
            """Return the live main runtime for session-scoped auxiliary routing."""
            return {
                "model": getattr(self, "model", "") or "",
                "provider": getattr(self, "provider", "") or "",
                "base_url": getattr(self, "base_url", "") or "",
                "api_key": getattr(self, "api_key", "") or "",
                "api_mode": getattr(self, "api_mode", "") or "",
            }


    def _is_direct_openai_url(self, base_url: str = None) -> bool:
            """Return True when a base URL targets OpenAI's native API."""
            if base_url is not None:
                hostname = base_url_hostname(base_url)
            else:
                hostname = getattr(self, "_base_url_hostname", "") or base_url_hostname(
                    getattr(self, "_base_url_lower", "")
                )
            return hostname == "api.openai.com"


    def _is_azure_openai_url(self, base_url: str = None) -> bool:
            """Return True when a base URL targets Azure OpenAI.

            Azure OpenAI exposes an OpenAI-compatible endpoint at
            ``{resource}.openai.azure.com/openai/v1`` that accepts the
            standard ``openai`` Python client.  Unlike api.openai.com it
            does NOT support the Responses API — gpt-5.x models are served
            on the regular ``/chat/completions`` path — so routing decisions
            must treat Azure separately from direct OpenAI.
            """
            if base_url is not None:
                url = str(base_url).lower()
            else:
                url = getattr(self, "_base_url_lower", "") or ""
            return "openai.azure.com" in url


    def _resolved_api_call_timeout(self) -> float:
            """Resolve the effective per-call request timeout in seconds.

            Priority:
              1. ``providers.<id>.models.<model>.timeout_seconds`` (per-model override)
              2. ``providers.<id>.request_timeout_seconds`` (provider-wide)
              3. ``HERMES_API_TIMEOUT`` env var (legacy escape hatch)
              4. 1800.0s default

            Used by OpenAI-wire chat completions (streaming and non-streaming) so
            the per-provider config knob wins over the 1800s default.  Without this
            helper, the hardcoded ``HERMES_API_TIMEOUT`` fallback would always be
            passed as a per-call ``timeout=`` kwarg, overriding the client-level
            timeout the AIAgent.__init__ path configured.
            """
            cfg = get_provider_request_timeout(self.provider, self.model)
            if cfg is not None:
                return cfg
            return float(os.getenv("HERMES_API_TIMEOUT", 1800.0))


    def _resolved_api_call_stale_timeout_base(self) -> tuple[float, bool]:
            """Resolve the base non-stream stale timeout and whether it is implicit.

            Priority:
              1. ``providers.<id>.models.<model>.stale_timeout_seconds``
              2. ``providers.<id>.stale_timeout_seconds``
              3. ``HERMES_API_CALL_STALE_TIMEOUT`` env var
              4. 300.0s default

            Returns ``(timeout_seconds, uses_implicit_default)`` so the caller can
            preserve legacy behaviors that only apply when the user has *not*
            explicitly configured a stale timeout, such as auto-disabling the
            detector for local endpoints.
            """
            cfg = get_provider_stale_timeout(self.provider, self.model)
            if cfg is not None:
                return cfg, False

            env_timeout = os.getenv("HERMES_API_CALL_STALE_TIMEOUT")
            if env_timeout is not None:
                return float(env_timeout), False

            return 300.0, True


    def _compute_non_stream_stale_timeout(self, messages: list[dict[str, Any]]) -> float:
            """Compute the effective non-stream stale timeout for this request."""
            stale_base, uses_implicit_default = self._resolved_api_call_stale_timeout_base()
            base_url = getattr(self, "_base_url", None) or self.base_url or ""
            if uses_implicit_default and base_url and is_local_endpoint(base_url):
                return float("inf")

            est_tokens = sum(len(str(v)) for v in messages) // 4
            if est_tokens > 100_000:
                return max(stale_base, 600.0)
            if est_tokens > 50_000:
                return max(stale_base, 450.0)
            return stale_base


    def _is_openrouter_url(self) -> bool:
            """Return True when the base URL targets OpenRouter."""
            return base_url_host_matches(self._base_url_lower, "openrouter.ai")


    def _anthropic_prompt_cache_policy(
            self,
            *,
            provider: Optional[str] = None,
            base_url: Optional[str] = None,
            api_mode: Optional[str] = None,
            model: Optional[str] = None,
        ) -> tuple[bool, bool]:
            """Decide whether to apply Anthropic prompt caching and which layout to use.

            Returns ``(should_cache, use_native_layout)``:
              * ``should_cache`` — inject ``cache_control`` breakpoints for this
                request (applies to OpenRouter Claude, native Anthropic, and
                third-party gateways that speak the native Anthropic protocol).
              * ``use_native_layout`` — place markers on the *inner* content
                blocks (native Anthropic accepts and requires this layout);
                when False markers go on the message envelope (OpenRouter and
                OpenAI-wire proxies expect the looser layout).

            Third-party providers using the native Anthropic transport
            (``api_mode == 'anthropic_messages'`` + Claude-named model) get
            caching with the native layout so they benefit from the same
            cost reduction as direct Anthropic callers, provided their
            gateway implements the Anthropic cache_control contract
            (MiniMax, Zhipu GLM, LiteLLM's Anthropic proxy mode all do).

            Qwen / Alibaba-family models on OpenCode, OpenCode Go, and direct
            Alibaba (DashScope) also honour Anthropic-style ``cache_control``
            markers on OpenAI-wire chat completions. Upstream pi-mono #3392 /
            pi #3393 documented this for opencode-go Qwen. Without markers
            these providers serve zero cache hits, re-billing the full prompt
            on every turn.
            """
            eff_provider = (provider if provider is not None else self.provider) or ""
            eff_base_url = base_url if base_url is not None else (self.base_url or "")
            eff_api_mode = api_mode if api_mode is not None else (self.api_mode or "")
            eff_model = (model if model is not None else self.model) or ""

            model_lower = eff_model.lower()
            provider_lower = eff_provider.lower()
            is_claude = "claude" in model_lower
            is_openrouter = base_url_host_matches(eff_base_url, "openrouter.ai")
            is_anthropic_wire = eff_api_mode == "anthropic_messages"
            is_native_anthropic = (
                is_anthropic_wire
                and (eff_provider == "anthropic" or base_url_hostname(eff_base_url) == "api.anthropic.com")
            )

            if is_native_anthropic:
                return True, True
            if is_openrouter and is_claude:
                return True, False
            if is_anthropic_wire and is_claude:
                # Third-party Anthropic-compatible gateway.
                return True, True

            # MiniMax on its Anthropic-compatible endpoint serves its own
            # model family (MiniMax-M2.7, M2.5, M2.1, M2) with documented
            # cache_control support (0.1× read pricing, 5-minute TTL).  The
            # blanket is_claude gate above excludes these — opt them in
            # explicitly via provider id or host match so users on
            # provider=minimax / minimax-cn (or custom endpoints pointing at
            # api.minimax.io/anthropic / api.minimaxi.com/anthropic) get the
            # same cost reduction as Claude traffic.
            # Docs: https://platform.minimax.io/docs/api-reference/anthropic-api-compatible-cache
            if is_anthropic_wire:
                is_minimax_provider = provider_lower in {"minimax", "minimax-cn"}
                is_minimax_host = (
                    base_url_host_matches(eff_base_url, "api.minimax.io")
                    or base_url_host_matches(eff_base_url, "api.minimaxi.com")
                )
                if is_minimax_provider or is_minimax_host:
                    return True, True

            # Qwen/Alibaba on OpenCode (Zen/Go) and native DashScope: OpenAI-wire
            # transport that accepts Anthropic-style cache_control markers and
            # rewards them with real cache hits.  Without this branch
            # qwen3.6-plus on opencode-go reports 0% cached tokens and burns
            # through the subscription on every turn.
            model_is_qwen = "qwen" in model_lower
            provider_is_alibaba_family = provider_lower in {
                "opencode", "opencode-zen", "opencode-go", "alibaba",
            }
            if provider_is_alibaba_family and model_is_qwen:
                # Envelope layout (native_anthropic=False): markers on inner
                # content parts, not top-level tool messages.  Matches
                # pi-mono's "alibaba" cacheControlFormat.
                return True, False

            return False, False


    def _model_requires_responses_api(model: str) -> bool:
            """Return True for models that require the Responses API path.

            GPT-5.x models are rejected on /v1/chat/completions by both
            OpenAI and OpenRouter (error: ``unsupported_api_for_model``).
            Detect these so the correct api_mode is set regardless of
            which provider is serving the model.
            """
            m = model.lower()
            # Strip vendor prefix (e.g. "openai/gpt-5.4" → "gpt-5.4")
            if "/" in m:
                m = m.rsplit("/", 1)[-1]
            return m.startswith("gpt-5")


    def _provider_model_requires_responses_api(
            model: str,
            *,
            provider: Optional[str] = None,
        ) -> bool:
            """Return True when this provider/model pair should use Responses API."""
            normalized_provider = (provider or "").strip().lower()
            if normalized_provider == "copilot":
                try:
                    from hermes_cli.models import _should_use_copilot_responses_api
                    return _should_use_copilot_responses_api(model)
                except Exception:
                    # Fall back to the generic GPT-5 rule if Copilot-specific
                    # logic is unavailable for any reason.
                    pass
            return AIAgent._model_requires_responses_api(model)


    def _max_tokens_param(self, value: int) -> dict:
            """Return the correct max tokens kwarg for the current provider.

            OpenAI's newer models (gpt-4o, o-series, gpt-5+) require
            'max_completion_tokens'. Azure OpenAI also requires
            'max_completion_tokens' for gpt-5.x models served via the
            OpenAI-compatible endpoint. OpenRouter, local models, and older
            OpenAI models use 'max_tokens'.
            """
            if self._is_direct_openai_url() or self._is_azure_openai_url():
                return {"max_completion_tokens": value}
            return {"max_tokens": value}


    def _is_ollama_glm_backend(self) -> bool:
            """Detect the narrow backend family affected by Ollama/GLM stop misreports."""
            model_lower = (self.model or "").lower()
            provider_lower = (self.provider or "").lower()
            if "glm" not in model_lower and provider_lower != "zai":
                return False
            if "ollama" in self._base_url_lower or ":11434" in self._base_url_lower:
                return True
            return bool(self.base_url and is_local_endpoint(self.base_url))


    def _cleanup_task_resources(self, task_id: str) -> None:
            """Clean up VM and browser resources for a given task.

            Skips ``cleanup_vm`` when the active terminal environment is marked
            persistent (``persistent_filesystem=True``) so that long-lived sandbox
            containers survive between turns. The idle reaper in
            ``terminal_tool._cleanup_inactive_envs`` still tears them down once
            ``terminal.lifetime_seconds`` is exceeded. Non-persistent backends are
            torn down per-turn as before to prevent resource leakage (the original
            intent of this hook for the Morph backend, see commit fbd3a2fd).
            """
            try:
                if is_persistent_env(task_id):
                    if self.verbose_logging:
                        logging.debug(
                            f"Skipping per-turn cleanup_vm for persistent env {task_id}; "
                            f"idle reaper will handle it."
                        )
                else:
                    cleanup_vm(task_id)
            except Exception as e:
                if self.verbose_logging:
                    logging.warning(f"Failed to cleanup VM for task {task_id}: {e}")
            try:
                cleanup_browser(task_id)
            except Exception as e:
                if self.verbose_logging:
                    logging.warning(f"Failed to cleanup browser for task {task_id}: {e}")


    def _touch_activity(self, desc: str) -> None:
            """Update the last-activity timestamp and description (thread-safe)."""
            self._last_activity_ts = time.time()
            self._last_activity_desc = desc


    def _capture_rate_limits(self, http_response: Any) -> None:
            """Parse x-ratelimit-* headers from an HTTP response and cache the state.

            Called after each streaming API call.  The httpx Response object is
            available on the OpenAI SDK Stream via ``stream.response``.
            """
            if http_response is None:
                return
            headers = getattr(http_response, "headers", None)
            if not headers:
                return
            try:
                from agent.rate_limit_tracker import parse_rate_limit_headers
                state = parse_rate_limit_headers(headers, provider=self.provider)
                if state is not None:
                    self._rate_limit_state = state
            except Exception:
                pass


    def get_rate_limit_state(self):
            """Return the last captured RateLimitState, or None."""
            return self._rate_limit_state


    def get_activity_summary(self) -> dict:
            """Return a snapshot of the agent's current activity for diagnostics.

            Called by the gateway timeout handler to report what the agent was doing
            when it was killed, and by the periodic "still working" notifications.
            """
            elapsed = time.time() - self._last_activity_ts
            return {
                "last_activity_ts": self._last_activity_ts,
                "last_activity_desc": self._last_activity_desc,
                "seconds_since_activity": round(elapsed, 1),
                "current_tool": self._current_tool,
                "api_call_count": self._api_call_count,
                "max_iterations": self.max_iterations,
                "budget_used": self.iteration_budget.used,
                "budget_max": self.iteration_budget.max_total,
            }


    def _get_tool_call_id_static(tc) -> str:
            """Extract call ID from a tool_call entry (dict or object)."""
            if isinstance(tc, dict):
                return tc.get("call_id", "") or tc.get("id", "") or ""
            return getattr(tc, "call_id", "") or getattr(tc, "id", "") or ""


    def _cap_delegate_task_calls(tool_calls: list) -> list:
            """Truncate excess delegate_task calls to max_concurrent_children.

            The delegate_tool caps the task list inside a single call, but the
            model can emit multiple separate delegate_task tool_calls in one
            turn.  This truncates the excess, preserving all non-delegate calls.

            Returns the original list if no truncation was needed.
            """
            from tools.delegate_tool import _get_max_concurrent_children
            max_children = _get_max_concurrent_children()
            delegate_count = sum(1 for tc in tool_calls if tc.function.name == "delegate_task")
            if delegate_count <= max_children:
                return tool_calls
            kept_delegates = 0
            truncated = []
            for tc in tool_calls:
                if tc.function.name == "delegate_task":
                    if kept_delegates < max_children:
                        truncated.append(tc)
                        kept_delegates += 1
                else:
                    truncated.append(tc)
            logger.warning(
                "Truncated %d excess delegate_task call(s) to enforce "
                "max_concurrent_children=%d limit",
                delegate_count - max_children, max_children,
            )
            return truncated


    def _deduplicate_tool_calls(tool_calls: list) -> list:
            """Remove duplicate (tool_name, arguments) pairs within a single turn.

            Only the first occurrence of each unique pair is kept.
            Returns the original list if no duplicates were found.
            """
            seen: set = set()
            unique: list = []
            for tc in tool_calls:
                key = (tc.function.name, tc.function.arguments)
                if key not in seen:
                    seen.add(key)
                    unique.append(tc)
                else:
                    logger.warning("Removed duplicate tool call: %s", tc.function.name)
            return unique if len(unique) < len(tool_calls) else tool_calls


    def _repair_tool_call(self, tool_name: str) -> str | None:
            """Attempt to repair a mismatched tool name before aborting.

            Models sometimes emit variants of a tool name that differ only
            in casing, separators, or class-like suffixes. Normalize
            aggressively before falling back to fuzzy match:

            1. Lowercase direct match.
            2. Lowercase + hyphens/spaces -> underscores.
            3. CamelCase -> snake_case (TodoTool -> todo_tool).
            4. Strip trailing ``_tool`` / ``-tool`` / ``tool`` suffix that
               Claude-style models sometimes tack on (TodoTool_tool ->
               TodoTool -> Todo -> todo). Applied twice so double-tacked
               suffixes like ``TodoTool_tool`` reduce all the way.
            5. Fuzzy match (difflib, cutoff=0.7).

            See #14784 for the original reports (TodoTool_tool, Patch_tool,
            BrowserClick_tool were all returning "Unknown tool" before).

            Returns the repaired name if found in valid_tool_names, else None.
            """
            import re
            from difflib import get_close_matches

            if not tool_name:
                return None

            def _norm(s: str) -> str:
                return s.lower().replace("-", "_").replace(" ", "_")

            def _camel_snake(s: str) -> str:
                return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()

            def _strip_tool_suffix(s: str) -> str | None:
                lc = s.lower()
                for suffix in ("_tool", "-tool", "tool"):
                    if lc.endswith(suffix):
                        return s[: -len(suffix)].rstrip("_-")
                return None

            # Cheap fast-paths first — these cover the common case.
            lowered = tool_name.lower()
            if lowered in self.valid_tool_names:
                return lowered
            normalized = _norm(tool_name)
            if normalized in self.valid_tool_names:
                return normalized

            # Build the full candidate set for class-like emissions.
            cands: set[str] = {tool_name, lowered, normalized, _camel_snake(tool_name)}
            # Strip trailing tool-suffix up to twice — TodoTool_tool needs it.
            for _ in range(2):
                extra: set[str] = set()
                for c in cands:
                    stripped = _strip_tool_suffix(c)
                    if stripped:
                        extra.add(stripped)
                        extra.add(_norm(stripped))
                        extra.add(_camel_snake(stripped))
                cands |= extra

            for c in cands:
                if c and c in self.valid_tool_names:
                    return c

            # Fuzzy match as last resort.
            matches = get_close_matches(lowered, self.valid_tool_names, n=1, cutoff=0.7)
            if matches:
                return matches[0]

            return None


    def _invalidate_system_prompt(self):
            """
            Invalidate the cached system prompt, forcing a rebuild on the next turn.

            Called after context compression events. Also reloads memory from disk
            so the rebuilt prompt captures any writes from this session.
            """
            self._cached_system_prompt = None
            if self._memory_store:
                self._memory_store.load_from_disk()


    def _deterministic_call_id(fn_name: str, arguments: str, index: int = 0) -> str:
            """Generate a deterministic call_id from tool call content.

            Used as a fallback when the API doesn't provide a call_id.
            Deterministic IDs prevent cache invalidation — random UUIDs would
            make every API call's prefix unique, breaking OpenAI's prompt cache.
            """
            return _codex_deterministic_call_id(fn_name, arguments, index)


    def _split_responses_tool_id(raw_id: Any) -> tuple[Optional[str], Optional[str]]:
            """Split a stored tool id into (call_id, response_item_id)."""
            return _codex_split_responses_tool_id(raw_id)


    def _derive_responses_function_call_id(
            self,
            call_id: str,
            response_item_id: Optional[str] = None,
        ) -> str:
            """Build a valid Responses `function_call.id` (must start with `fc_`)."""
            return _codex_derive_responses_function_call_id(call_id, response_item_id)


    def _thread_identity(self) -> str:
            thread = threading.current_thread()
            return f"{thread.name}:{thread.ident}"


    def _is_qwen_portal(self) -> bool:
            """Return True when the base URL targets Qwen Portal."""
            return base_url_host_matches(self._base_url_lower, "portal.qwen.ai")


