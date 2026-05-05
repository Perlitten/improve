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

class ResponseParsingMixin:
    def _strip_think_blocks(self, content: str) -> str:
            """Remove reasoning/thinking blocks from content, returning only visible text.

            Handles four cases:
              1. Closed tag pairs (``<think>…</think>``) — the common path when
                 the provider emits complete reasoning blocks.
              2. Unterminated open tag at a block boundary (start of text or
                 after a newline) — e.g. MiniMax M2.7 / NIM endpoints where the
                 closing tag is dropped.  Everything from the open tag to end
                 of string is stripped.  The block-boundary check mirrors
                 ``gateway/stream_consumer.py``'s filter so models that mention
                 ``<think>`` in prose aren't over-stripped.
              3. Stray orphan open/close tags that slip through.
              4. Tag variants: ``<think>``, ``<thinking>``, ``<reasoning>``,
                 ``<REASONING_SCRATCHPAD>``, ``<thought>`` (Gemma 4), all
                 case-insensitive.

            Additionally strips standalone tool-call XML blocks that some open
            models (notably Gemma variants on OpenRouter) emit inside assistant
            content instead of via the structured ``tool_calls`` field:
              * ``<tool_call>…</tool_call>``
              * ``<tool_calls>…</tool_calls>``
              * ``<tool_result>…</tool_result>``
              * ``<function_call>…</function_call>``
              * ``<function_calls>…</function_calls>``
              * ``<function name="…">…</function>`` (Gemma style)
            Ported from openclaw/openclaw#67318. The ``<function>`` variant is
            boundary-gated (only strips when the tag sits at start-of-line or
            after punctuation and carries a ``name="..."`` attribute) so prose
            mentions like "Use <function> in JavaScript" are preserved.
            """
            if not content:
                return ""
            # 1. Closed tag pairs — case-insensitive for all variants so
            #    mixed-case tags (<THINK>, <Thinking>) don't slip through to
            #    the unterminated-tag pass and take trailing content with them.
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<reasoning>.*?</reasoning>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<REASONING_SCRATCHPAD>.*?</REASONING_SCRATCHPAD>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<thought>.*?</thought>', '', content, flags=re.DOTALL | re.IGNORECASE)
            # 1b. Tool-call XML blocks (openclaw/openclaw#67318). Handle the
            #     generic tag names first — they have no attribute gating since
            #     a literal <tool_call> in prose is already vanishingly rare.
            for _tc_name in ("tool_call", "tool_calls", "tool_result",
                              "function_call", "function_calls"):
                content = re.sub(
                    rf'<{_tc_name}\b[^>]*>.*?</{_tc_name}>',
                    '',
                    content,
                    flags=re.DOTALL | re.IGNORECASE,
                )
            # 1c. <function name="...">...</function> — Gemma-style standalone
            #     tool call. Only strip when the tag sits at a block boundary
            #     (start of text, after a newline, or after sentence-ending
            #     punctuation) AND carries a name="..." attribute. This keeps
            #     prose mentions like "Use <function> to declare" safe.
            content = re.sub(
                r'(?:(?<=^)|(?<=[\n\r.!?:]))[ \t]*'
                r'<function\b[^>]*\bname\s*=[^>]*>'
                r'(?:(?:(?!</function>).)*)</function>',
                '',
                content,
                flags=re.DOTALL | re.IGNORECASE,
            )
            # 2. Unterminated reasoning block — open tag at a block boundary
            #    (start of text, or after a newline) with no matching close.
            #    Strip from the tag to end of string.  Fixes #8878 / #9568
            #    (MiniMax M2.7 leaking raw reasoning into assistant content).
            content = re.sub(
                r'(?:^|\n)[ \t]*<(?:think|thinking|reasoning|thought|REASONING_SCRATCHPAD)\b[^>]*>.*$',
                '',
                content,
                flags=re.DOTALL | re.IGNORECASE,
            )
            # 3. Stray orphan open/close tags that slipped through.
            content = re.sub(
                r'</?(?:think|thinking|reasoning|thought|REASONING_SCRATCHPAD)>\s*',
                '',
                content,
                flags=re.IGNORECASE,
            )
            # 3b. Stray tool-call closers. (We do NOT strip bare <function> or
            #     unterminated <function name="..."> because a truncated tail
            #     during streaming may still be valuable to the user; matches
            #     OpenClaw's intentional asymmetry.)
            content = re.sub(
                r'</(?:tool_call|tool_calls|tool_result|function_call|function_calls|function)>\s*',
                '',
                content,
                flags=re.IGNORECASE,
            )
            return content


    def _has_content_after_think_block(self, content: str) -> bool:
            """
            Check if content has actual text after any reasoning/thinking blocks.

            This detects cases where the model only outputs reasoning but no actual
            response, which indicates an incomplete generation that should be retried.
            Must stay in sync with _strip_think_blocks() tag variants.

            Args:
                content: The assistant message content to check

            Returns:
                True if there's meaningful content after think blocks, False otherwise
            """
            if not content:
                return False

            # Remove all reasoning tag variants (must match _strip_think_blocks)
            cleaned = self._strip_think_blocks(content)

            # Check if there's any non-whitespace content remaining
            return bool(cleaned.strip())


    def _looks_like_codex_intermediate_ack(
            self,
            user_message: str,
            assistant_content: str,
            messages: List[Dict[str, Any]],
        ) -> bool:
            """Detect a planning/ack message that should continue instead of ending the turn."""
            if any(isinstance(msg, dict) and msg.get("role") == "tool" for msg in messages):
                return False

            assistant_text = self._strip_think_blocks(assistant_content or "").strip().lower()
            if not assistant_text:
                return False
            if len(assistant_text) > 1200:
                return False

            has_future_ack = bool(
                re.search(r"\b(i['’]ll|i will|let me|i can do that|i can help with that)\b", assistant_text)
            )
            if not has_future_ack:
                return False

            action_markers = (
                "look into",
                "look at",
                "inspect",
                "scan",
                "check",
                "analyz",
                "review",
                "explore",
                "read",
                "open",
                "run",
                "test",
                "fix",
                "debug",
                "search",
                "find",
                "walkthrough",
                "report back",
                "summarize",
            )
            workspace_markers = (
                "directory",
                "current directory",
                "current dir",
                "cwd",
                "repo",
                "repository",
                "codebase",
                "project",
                "folder",
                "filesystem",
                "file tree",
                "files",
                "path",
            )

            user_text = (user_message or "").strip().lower()
            user_targets_workspace = (
                any(marker in user_text for marker in workspace_markers)
                or "~/" in user_text
                or "/" in user_text
            )
            assistant_mentions_action = any(marker in assistant_text for marker in action_markers)
            assistant_targets_workspace = any(
                marker in assistant_text for marker in workspace_markers
            )
            return (user_targets_workspace or assistant_targets_workspace) and assistant_mentions_action


    def _extract_reasoning(self, assistant_message) -> Optional[str]:
            """
            Extract reasoning/thinking content from an assistant message.

            OpenRouter and various providers can return reasoning in multiple formats:
            1. message.reasoning - Direct reasoning field (DeepSeek, Qwen, etc.)
            2. message.reasoning_content - Alternative field (Moonshot AI, Novita, etc.)
            3. message.reasoning_details - Array of {type, summary, ...} objects (OpenRouter unified)

            Args:
                assistant_message: The assistant message object from the API response

            Returns:
                Combined reasoning text, or None if no reasoning found
            """
            reasoning_parts = []

            # Check direct reasoning field
            if hasattr(assistant_message, 'reasoning') and assistant_message.reasoning:
                reasoning_parts.append(assistant_message.reasoning)

            # Check reasoning_content field (alternative name used by some providers)
            if hasattr(assistant_message, 'reasoning_content') and assistant_message.reasoning_content:
                # Don't duplicate if same as reasoning
                if assistant_message.reasoning_content not in reasoning_parts:
                    reasoning_parts.append(assistant_message.reasoning_content)

            # Check reasoning_details array (OpenRouter unified format)
            # Format: [{"type": "reasoning.summary", "summary": "...", ...}, ...]
            if hasattr(assistant_message, 'reasoning_details') and assistant_message.reasoning_details:
                for detail in assistant_message.reasoning_details:
                    if isinstance(detail, dict):
                        # Extract summary from reasoning detail object
                        summary = (
                            detail.get('summary')
                            or detail.get('thinking')
                            or detail.get('content')
                            or detail.get('text')
                        )
                        if summary and summary not in reasoning_parts:
                            reasoning_parts.append(summary)

            # Some providers embed reasoning directly inside assistant content
            # instead of returning structured reasoning fields.  Only fall back
            # to inline extraction when no structured reasoning was found.
            content = getattr(assistant_message, "content", None)
            if not reasoning_parts and isinstance(content, str) and content:
                inline_patterns = (
                    r"<think>(.*?)</think>",
                    r"<thinking>(.*?)</thinking>",
                    r"<thought>(.*?)</thought>",
                    r"<reasoning>(.*?)</reasoning>",
                    r"<REASONING_SCRATCHPAD>(.*?)</REASONING_SCRATCHPAD>",
                )
                for pattern in inline_patterns:
                    flags = re.DOTALL | re.IGNORECASE
                    for block in re.findall(pattern, content, flags=flags):
                        cleaned = block.strip()
                        if cleaned and cleaned not in reasoning_parts:
                            reasoning_parts.append(cleaned)

            # Combine all reasoning parts
            if reasoning_parts:
                return "\n\n".join(reasoning_parts)

            return None


    def _should_treat_stop_as_truncated(
            self,
            finish_reason: str,
            assistant_message,
            messages: Optional[list] = None,
        ) -> bool:
            """Detect conservative stop->length misreports for Ollama-hosted GLM models."""
            if finish_reason != "stop" or self.api_mode != "chat_completions":
                return False
            if not self._is_ollama_glm_backend():
                return False
            if not any(
                isinstance(msg, dict) and msg.get("role") == "tool"
                for msg in (messages or [])
            ):
                return False
            if assistant_message is None or getattr(assistant_message, "tool_calls", None):
                return False

            content = getattr(assistant_message, "content", None)
            if not isinstance(content, str):
                return False

            visible_text = self._strip_think_blocks(content).strip()
            if not visible_text:
                return False
            if len(visible_text) < 20 or not re.search(r"\s", visible_text):
                return False

            return not self._has_natural_response_ending(visible_text)


    def _has_natural_response_ending(content: str) -> bool:
            """Heuristic: does visible assistant text look intentionally finished?"""
            if not content:
                return False
            stripped = content.rstrip()
            if not stripped:
                return False
            if stripped.endswith("```"):
                return True
            return stripped[-1] in '.!?:)"\']}。！？：）】」』》'


    def _check_compression_model_feasibility(self) -> None:
            """Warn at session start if the auxiliary compression model's context
            window is smaller than the main model's compression threshold.

            When the auxiliary model cannot fit the content that needs summarising,
            compression will either fail outright (the LLM call errors) or produce
            a severely truncated summary.

            Called during ``__init__`` so CLI users see the warning immediately
            (via ``_vprint``).  The gateway sets ``status_callback`` *after*
            construction, so ``_replay_compression_warning()`` re-sends the
            stored warning through the callback on the first
            ``run_conversation()`` call.
            """
            if not self.compression_enabled:
                return
            try:
                from agent.auxiliary_client import (
                    _resolve_task_provider_model,
                    get_text_auxiliary_client,
                )
                from agent.model_metadata import (
                    MINIMUM_CONTEXT_LENGTH,
                    get_model_context_length,
                )

                client, aux_model = get_text_auxiliary_client(
                    "compression",
                    main_runtime=self._current_main_runtime(),
                )
                # Best-effort aux provider label for the warning message. The
                # configured provider may be "auto", in which case we fall back
                # to the client's base_url hostname so the user can still tell
                # where the compression model is actually being called.
                try:
                    _aux_cfg_provider, _, _, _, _ = _resolve_task_provider_model("compression")
                except Exception:
                    _aux_cfg_provider = ""
                if client is None or not aux_model:
                    msg = (
                        "⚠ No auxiliary LLM provider configured — context "
                        "compression will drop middle turns without a summary. "
                        "Run `hermes setup` or set OPENROUTER_API_KEY."
                    )
                    self._compression_warning = msg
                    self._emit_status(msg)
                    logger.warning(
                        "No auxiliary LLM provider for compression — "
                        "summaries will be unavailable."
                    )
                    return

                aux_base_url = str(getattr(client, "base_url", ""))
                aux_api_key = str(getattr(client, "api_key", ""))

                aux_context = get_model_context_length(
                    aux_model,
                    base_url=aux_base_url,
                    api_key=aux_api_key,
                    config_context_length=getattr(self, "_aux_compression_context_length_config", None),
                    provider=getattr(self, "provider", ""),
                )

                # Hard floor: the auxiliary compression model must have at least
                # MINIMUM_CONTEXT_LENGTH (64K) tokens of context.  The main model
                # is already required to meet this floor (checked earlier in
                # __init__), so the compression model must too — otherwise it
                # cannot summarise a full threshold-sized window of main-model
                # content.  Mirrors the main-model rejection pattern.
                if aux_context and aux_context < MINIMUM_CONTEXT_LENGTH:
                    raise ValueError(
                        f"Auxiliary compression model {aux_model} has a context "
                        f"window of {aux_context:,} tokens, which is below the "
                        f"minimum {MINIMUM_CONTEXT_LENGTH:,} required by Hermes "
                        f"Agent.  Choose a compression model with at least "
                        f"{MINIMUM_CONTEXT_LENGTH // 1000}K context (set "
                        f"auxiliary.compression.model in config.yaml), or set "
                        f"auxiliary.compression.context_length to override the "
                        f"detected value if it is wrong."
                    )

                threshold = self.context_compressor.threshold_tokens
                if aux_context < threshold:
                    # Auto-correct: lower the live session threshold so
                    # compression actually works this session.  The hard floor
                    # above guarantees aux_context >= MINIMUM_CONTEXT_LENGTH,
                    # so the new threshold is always >= 64K.
                    #
                    # The compression summariser sends a single user-role
                    # prompt (no system prompt, no tools) to the aux model, so
                    # new_threshold == aux_context is safe: the request is
                    # the raw messages plus a small summarisation instruction.
                    old_threshold = threshold
                    new_threshold = aux_context
                    self.context_compressor.threshold_tokens = new_threshold
                    # Keep threshold_percent in sync so future main-model
                    # context_length changes (update_model) re-derive from a
                    # sensible number rather than the original too-high value.
                    main_ctx = self.context_compressor.context_length
                    if main_ctx:
                        self.context_compressor.threshold_percent = (
                            new_threshold / main_ctx
                        )
                    safe_pct = int((aux_context / main_ctx) * 100) if main_ctx else 50
                    # Build human-readable "model (provider)" labels for both
                    # the main model and the compression model so users can
                    # tell at a glance which provider each side is actually
                    # using. When the configured provider is empty or "auto",
                    # fall back to the client's base_url hostname.
                    _main_model = getattr(self, "model", "") or "?"
                    _main_provider = getattr(self, "provider", "") or ""
                    _aux_provider_label = (
                        _aux_cfg_provider
                        if _aux_cfg_provider and _aux_cfg_provider != "auto"
                        else ""
                    )
                    if not _aux_provider_label:
                        try:
                            from urllib.parse import urlparse
                            _aux_provider_label = (
                                urlparse(aux_base_url).hostname or aux_base_url
                            )
                        except Exception:
                            _aux_provider_label = aux_base_url or "auto"
                    _main_label = (
                        f"{_main_model} ({_main_provider})"
                        if _main_provider
                        else _main_model
                    )
                    _aux_label = f"{aux_model} ({_aux_provider_label})"
                    msg = (
                        f"⚠ Compression model {_aux_label} context is "
                        f"{aux_context:,} tokens, but the main model "
                        f"{_main_label}'s compression threshold was "
                        f"{old_threshold:,} tokens. "
                        f"Auto-lowered this session's threshold to "
                        f"{new_threshold:,} tokens so compression can run.\n"
                        f"  To make this permanent, edit config.yaml — either:\n"
                        f"  1. Use a larger compression model:\n"
                        f"       auxiliary:\n"
                        f"         compression:\n"
                        f"           model: <model-with-{old_threshold:,}+-context>\n"
                        f"  2. Lower the compression threshold:\n"
                        f"       compression:\n"
                        f"         threshold: 0.{safe_pct:02d}"
                    )
                    self._compression_warning = msg
                    self._emit_status(msg)
                    logger.warning(
                        "Auxiliary compression model %s has %d token context, "
                        "below the main model's compression threshold of %d "
                        "tokens — auto-lowered session threshold to %d to "
                        "keep compression working.",
                        aux_model,
                        aux_context,
                        old_threshold,
                        new_threshold,
                    )
            except ValueError:
                # Hard rejections (aux below minimum context) must propagate
                # so the session refuses to start.
                raise
            except Exception as exc:
                logger.debug(
                    "Compression feasibility check failed (non-fatal): %s", exc
                )


    def _replay_compression_warning(self) -> None:
            """Re-send the compression warning through ``status_callback``.

            During ``__init__`` the gateway's ``status_callback`` is not yet
            wired, so ``_emit_status`` only reaches ``_vprint`` (CLI).  This
            method is called once at the start of the first
            ``run_conversation()`` — by then the gateway has set the callback,
            so every platform (Telegram, Discord, Slack, etc.) receives the
            warning.
            """
            msg = getattr(self, "_compression_warning", None)
            if msg and self.status_callback:
                try:
                    self.status_callback("lifecycle", msg)
                except Exception:
                    pass


