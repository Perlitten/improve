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

class PromptingMixin:
    def _build_system_prompt(self, system_message: str = None) -> str:
            """
            Assemble the full system prompt from all layers.

            Called once per session (cached on self._cached_system_prompt) and only
            rebuilt after context compression events. This ensures the system prompt
            is stable across all turns in a session, maximizing prefix cache hits.
            """
            # Layers (in order):
            #   1. Agent identity — SOUL.md when available, else DEFAULT_AGENT_IDENTITY
            #   2. User / gateway system prompt (if provided)
            #   3. Persistent memory (frozen snapshot)
            #   4. Skills guidance (if skills tools are loaded)
            #   5. Context files (AGENTS.md, .cursorrules — SOUL.md excluded here when used as identity)
            #   6. Current date & time (frozen at build time)
            #   7. Platform-specific formatting hint

            # Try SOUL.md as primary identity unless the caller explicitly skipped it.
            # Some execution modes (cron) still want HERMES_HOME persona while keeping
            # cwd project instructions disabled.
            _soul_loaded = False
            if self.load_soul_identity or not self.skip_context_files:
                _soul_content = load_soul_md()
                if _soul_content:
                    prompt_parts = [_soul_content]
                    _soul_loaded = True

            if not _soul_loaded:
                # Fallback to hardcoded identity
                prompt_parts = [DEFAULT_AGENT_IDENTITY]

            # Pointer to the hermes-agent skill + docs for user questions about Hermes itself.
            prompt_parts.append(HERMES_AGENT_HELP_GUIDANCE)

            # Tool-aware behavioral guidance: only inject when the tools are loaded
            tool_guidance = []
            if "memory" in self.valid_tool_names:
                tool_guidance.append(MEMORY_GUIDANCE)
            if "session_search" in self.valid_tool_names:
                tool_guidance.append(SESSION_SEARCH_GUIDANCE)
            if "skill_manage" in self.valid_tool_names:
                tool_guidance.append(SKILLS_GUIDANCE)
            # Kanban worker/orchestrator lifecycle — only present when the
            # dispatcher spawned this process (kanban_show check_fn gates on
            # HERMES_KANBAN_TASK env var). Normal chat sessions never see
            # this block.
            if "kanban_show" in self.valid_tool_names:
                tool_guidance.append(KANBAN_GUIDANCE)
            if tool_guidance:
                prompt_parts.append(" ".join(tool_guidance))

            nous_subscription_prompt = build_nous_subscription_prompt(self.valid_tool_names)
            if nous_subscription_prompt:
                prompt_parts.append(nous_subscription_prompt)
            # Tool-use enforcement: tells the model to actually call tools instead
            # of describing intended actions.  Controlled by config.yaml
            # agent.tool_use_enforcement:
            #   "auto" (default) — matches TOOL_USE_ENFORCEMENT_MODELS
            #   true  — always inject (all models)
            #   false — never inject
            #   list  — custom model-name substrings to match
            if self.valid_tool_names:
                _enforce = self._tool_use_enforcement
                _inject = False
                if _enforce is True or (isinstance(_enforce, str) and _enforce.lower() in ("true", "always", "yes", "on")):
                    _inject = True
                elif _enforce is False or (isinstance(_enforce, str) and _enforce.lower() in ("false", "never", "no", "off")):
                    _inject = False
                elif isinstance(_enforce, list):
                    model_lower = (self.model or "").lower()
                    _inject = any(p.lower() in model_lower for p in _enforce if isinstance(p, str))
                else:
                    # "auto" or any unrecognised value — use hardcoded defaults
                    model_lower = (self.model or "").lower()
                    _inject = any(p in model_lower for p in TOOL_USE_ENFORCEMENT_MODELS)
                if _inject:
                    prompt_parts.append(TOOL_USE_ENFORCEMENT_GUIDANCE)
                    _model_lower = (self.model or "").lower()
                    # Google model operational guidance (conciseness, absolute
                    # paths, parallel tool calls, verify-before-edit, etc.)
                    if "gemini" in _model_lower or "gemma" in _model_lower:
                        prompt_parts.append(GOOGLE_MODEL_OPERATIONAL_GUIDANCE)
                    # OpenAI GPT/Codex execution discipline (tool persistence,
                    # prerequisite checks, verification, anti-hallucination).
                    if "gpt" in _model_lower or "codex" in _model_lower:
                        prompt_parts.append(OPENAI_MODEL_EXECUTION_GUIDANCE)

            # so it can refer the user to them rather than reinventing answers.

            # Note: ephemeral_system_prompt is NOT included here. It's injected at
            # API-call time only so it stays out of the cached/stored system prompt.
            if system_message is not None:
                prompt_parts.append(system_message)

            if self._memory_store:
                if self._memory_enabled:
                    mem_block = self._memory_store.format_for_system_prompt("memory")
                    if mem_block:
                        prompt_parts.append(mem_block)
                # USER.md is always included when enabled.
                if self._user_profile_enabled:
                    user_block = self._memory_store.format_for_system_prompt("user")
                    if user_block:
                        prompt_parts.append(user_block)

            # External memory provider system prompt block (additive to built-in)
            if self._memory_manager:
                try:
                    _ext_mem_block = self._memory_manager.build_system_prompt()
                    if _ext_mem_block:
                        prompt_parts.append(_ext_mem_block)
                except Exception:
                    pass

            has_skills_tools = any(name in self.valid_tool_names for name in ['skills_list', 'skill_view', 'skill_manage'])
            if has_skills_tools:
                avail_toolsets = {
                    toolset
                    for toolset in (
                        get_toolset_for_tool(tool_name) for tool_name in self.valid_tool_names
                    )
                    if toolset
                }
                skills_prompt = build_skills_system_prompt(
                    available_tools=self.valid_tool_names,
                    available_toolsets=avail_toolsets,
                )
            else:
                skills_prompt = ""
            if skills_prompt:
                prompt_parts.append(skills_prompt)

            if not self.skip_context_files:
                # Use TERMINAL_CWD for context file discovery when set (gateway
                # mode).  The gateway process runs from the hermes-agent install
                # dir, so os.getcwd() would pick up the repo's AGENTS.md and
                # other dev files — inflating token usage by ~10k for no benefit.
                _context_cwd = os.getenv("TERMINAL_CWD") or None
                context_files_prompt = build_context_files_prompt(
                    cwd=_context_cwd, skip_soul=_soul_loaded)
                if context_files_prompt:
                    prompt_parts.append(context_files_prompt)

            from hermes_time import now as _hermes_now
            now = _hermes_now()
            timestamp_line = f"Conversation started: {now.strftime('%A, %B %d, %Y %I:%M %p')}"
            if self.pass_session_id and self.session_id:
                timestamp_line += f"\nSession ID: {self.session_id}"
            if self.model:
                timestamp_line += f"\nModel: {self.model}"
            if self.provider:
                timestamp_line += f"\nProvider: {self.provider}"
            prompt_parts.append(timestamp_line)

            # Alibaba Coding Plan API always returns "glm-4.7" as model name regardless
            # of the requested model. Inject explicit model identity into the system prompt
            # so the agent can correctly report which model it is (workaround for API bug).
            if self.provider == "alibaba":
                _model_short = self.model.split("/")[-1] if "/" in self.model else self.model
                prompt_parts.append(
                    f"You are powered by the model named {_model_short}. "
                    f"The exact model ID is {self.model}. "
                    f"When asked what model you are, always answer based on this information, "
                    f"not on any model name returned by the API."
                )

            # Environment hints (WSL, Termux, etc.) — tell the agent about the
            # execution environment so it can translate paths and adapt behavior.
            _env_hints = build_environment_hints()
            if _env_hints:
                prompt_parts.append(_env_hints)

            platform_key = (self.platform or "").lower().strip()
            if platform_key in PLATFORM_HINTS:
                prompt_parts.append(PLATFORM_HINTS[platform_key])
            elif platform_key:
                # Check plugin registry for platform-specific LLM guidance
                try:
                    from gateway.platform_registry import platform_registry
                    _entry = platform_registry.get(platform_key)
                    if _entry and _entry.platform_hint:
                        prompt_parts.append(_entry.platform_hint)
                except Exception:
                    pass

            return "\n\n".join(p.strip() for p in prompt_parts if p.strip())


    def _format_tools_for_system_message(self) -> str:
            """
            Format tool definitions for the system message in the trajectory format.

            Returns:
                str: JSON string representation of tool definitions
            """
            if not self.tools:
                return "[]"

            # Convert tool definitions to the format expected in trajectories
            formatted_tools = []
            for tool in self.tools:
                func = tool["function"]
                formatted_tool = {
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {}),
                    "required": None  # Match the format in the example
                }
                formatted_tools.append(formatted_tool)

            return json.dumps(formatted_tools, ensure_ascii=False)


    def _sanitize_api_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            """Fix orphaned tool_call / tool_result pairs before every LLM call.

            Runs unconditionally — not gated on whether the context compressor
            is present — so orphans from session loading or manual message
            manipulation are always caught.
            """
            # --- Role allowlist: drop messages with roles the API won't accept ---
            filtered = []
            for msg in messages:
                role = msg.get("role")
                if role not in AIAgent._VALID_API_ROLES:
                    logger.debug(
                        "Pre-call sanitizer: dropping message with invalid role %r",
                        role,
                    )
                    continue
                filtered.append(msg)
            messages = filtered

            surviving_call_ids: set = set()
            for msg in messages:
                if msg.get("role") == "assistant":
                    for tc in msg.get("tool_calls") or []:
                        cid = AIAgent._get_tool_call_id_static(tc)
                        if cid:
                            surviving_call_ids.add(cid)

            result_call_ids: set = set()
            for msg in messages:
                if msg.get("role") == "tool":
                    cid = msg.get("tool_call_id")
                    if cid:
                        result_call_ids.add(cid)

            # 1. Drop tool results with no matching assistant call
            orphaned_results = result_call_ids - surviving_call_ids
            if orphaned_results:
                messages = [
                    m for m in messages
                    if not (m.get("role") == "tool" and m.get("tool_call_id") in orphaned_results)
                ]
                logger.debug(
                    "Pre-call sanitizer: removed %d orphaned tool result(s)",
                    len(orphaned_results),
                )

            # 2. Inject stub results for calls whose result was dropped
            missing_results = surviving_call_ids - result_call_ids
            if missing_results:
                patched: List[Dict[str, Any]] = []
                for msg in messages:
                    patched.append(msg)
                    if msg.get("role") == "assistant":
                        for tc in msg.get("tool_calls") or []:
                            cid = AIAgent._get_tool_call_id_static(tc)
                            if cid in missing_results:
                                patched.append({
                                    "role": "tool",
                                    "content": "[Result unavailable — see context summary above]",
                                    "tool_call_id": cid,
                                })
                messages = patched
                logger.debug(
                    "Pre-call sanitizer: added %d stub tool result(s)",
                    len(missing_results),
                )
            return messages


    def _is_thinking_only_assistant(msg: Dict[str, Any]) -> bool:
            """Return True if ``msg`` is an assistant turn whose only payload is reasoning.

            "Thinking-only" means the model emitted reasoning (``reasoning`` or
            ``reasoning_content``) but no visible text and no tool_calls. When sent
            back to providers that convert reasoning into thinking blocks (native
            Anthropic, OpenRouter Anthropic, third-party Anthropic-compatible
            gateways), the resulting message has only thinking blocks — which
            Anthropic rejects with HTTP 400 "The final block in an assistant
            message cannot be `thinking`."

            Symmetric with Claude Code's ``filterOrphanedThinkingOnlyMessages``
            (src/utils/messages.ts). We drop the whole turn from the API copy
            rather than fabricating stub text — the message log (UI transcript)
            keeps the reasoning block; only the wire copy is cleaned.
            """
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                return False
            if msg.get("tool_calls"):
                return False
            # Does it have any actual output?
            content = msg.get("content")
            if isinstance(content, str):
                if content.strip():
                    return False
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        if block:  # non-empty non-dict string etc.
                            return False
                        continue
                    btype = block.get("type")
                    if btype in ("thinking", "redacted_thinking"):
                        continue
                    if btype == "text":
                        text = block.get("text", "")
                        if isinstance(text, str) and text.strip():
                            return False
                        continue
                    # tool_use, image, document, etc. — real payload
                    return False
            elif content is not None and content != "":
                return False
            # Content is empty-ish. Is there reasoning to make it thinking-only?
            reasoning = msg.get("reasoning_content") or msg.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                return True
            # reasoning_details list form
            rd = msg.get("reasoning_details")
            if isinstance(rd, list) and rd:
                return True
            return False


    def _drop_thinking_only_and_merge_users(
            messages: List[Dict[str, Any]],
        ) -> List[Dict[str, Any]]:
            """Drop thinking-only assistant turns; merge any adjacent user messages left behind.

            Runs on the per-call ``api_messages`` copy only. The stored
            conversation history (``self.messages``) is never mutated, so the
            user still sees the thinking block in the CLI/gateway transcript and
            session persistence keeps the full trace. Only the wire copy sent to
            the provider is cleaned.

            Why drop-and-merge rather than inject stub text:
            - Fabricating ``"."`` / ``"(continued)"`` text lies in the history
              and makes future turns see model output the model didn't emit.
            - Dropping the turn preserves honesty; merging adjacent user messages
              preserves the provider's role-alternation invariant.
            - This is the pattern used by Claude Code's ``normalizeMessagesForAPI``
              (filterOrphanedThinkingOnlyMessages + mergeAdjacentUserMessages).
            """
            if not messages:
                return messages

            # Pass 1: drop thinking-only assistant turns.
            kept = [m for m in messages if not AIAgent._is_thinking_only_assistant(m)]
            dropped = len(messages) - len(kept)
            if dropped == 0:
                return messages

            # Pass 2: merge any newly-adjacent user messages.
            merged: List[Dict[str, Any]] = []
            merges = 0
            for m in kept:
                prev = merged[-1] if merged else None
                if (
                    prev is not None
                    and prev.get("role") == "user"
                    and m.get("role") == "user"
                ):
                    prev_content = prev.get("content", "")
                    cur_content = m.get("content", "")
                    # Work on a copy of ``prev`` so the caller's input dicts are
                    # never mutated. ``_sanitize_api_messages`` upstream already
                    # hands us per-call copies, but staying pure here means we
                    # can be called safely from anywhere (tests, other loops).
                    prev_copy = dict(prev)
                    # Only string-content merge is meaningful for role-alternation
                    # purposes. If either side is a list (multimodal), append as a
                    # separate block rather than collapsing.
                    if isinstance(prev_content, str) and isinstance(cur_content, str):
                        sep = "\n\n" if prev_content and cur_content else ""
                        prev_copy["content"] = prev_content + sep + cur_content
                    elif isinstance(prev_content, list) and isinstance(cur_content, list):
                        prev_copy["content"] = list(prev_content) + list(cur_content)
                    elif isinstance(prev_content, list) and isinstance(cur_content, str):
                        if cur_content:
                            prev_copy["content"] = list(prev_content) + [
                                {"type": "text", "text": cur_content}
                            ]
                        else:
                            prev_copy["content"] = list(prev_content)
                    elif isinstance(prev_content, str) and isinstance(cur_content, list):
                        new_blocks: List[Dict[str, Any]] = []
                        if prev_content:
                            new_blocks.append({"type": "text", "text": prev_content})
                        new_blocks.extend(cur_content)
                        prev_copy["content"] = new_blocks
                    else:
                        # Unknown content shape — fall back to appending separately
                        # (violates alternation, but safer than raising in a hot path).
                        merged.append(m)
                        continue
                    merged[-1] = prev_copy
                    merges += 1
                else:
                    merged.append(m)

            logger.debug(
                "Pre-call sanitizer: dropped %d thinking-only assistant turn(s), "
                "merged %d adjacent user message(s)",
                dropped,
                merges,
            )
            return merged


    def _compress_context(self, messages: list, system_message: str, *, approx_tokens: int = None, task_id: str = "default", focus_topic: str = None) -> tuple:
            """Compress conversation context and split the session in SQLite.

            Args:
                focus_topic: Optional focus string for guided compression — the
                    summariser will prioritise preserving information related to
                    this topic.  Inspired by Claude Code's ``/compact <focus>``.

            Returns:
                (compressed_messages, new_system_prompt) tuple
            """
            _pre_msg_count = len(messages)
            logger.info(
                "context compression started: session=%s messages=%d tokens=~%s model=%s focus=%r",
                self.session_id or "none", _pre_msg_count,
                f"{approx_tokens:,}" if approx_tokens else "unknown", self.model,
                focus_topic,
            )

            # Notify external memory provider before compression discards context
            if self._memory_manager:
                try:
                    self._memory_manager.on_pre_compress(messages)
                except Exception:
                    pass

            try:
                compressed = self.context_compressor.compress(messages, current_tokens=approx_tokens, focus_topic=focus_topic)
            except TypeError:
                # Plugin context engine with strict signature that doesn't accept
                # focus_topic — fall back to calling without it.
                compressed = self.context_compressor.compress(messages, current_tokens=approx_tokens)

            summary_error = getattr(self.context_compressor, "_last_summary_error", None)
            if summary_error:
                if getattr(self, "_last_compression_summary_warning", None) != summary_error:
                    self._last_compression_summary_warning = summary_error
                    self._emit_warning(
                        f"⚠ Compression summary failed: {summary_error}. "
                        "Inserted a fallback context marker."
                    )
            else:
                # No hard failure — but did the configured aux model error out
                # and get recovered by retrying on main?  Surface that so users
                # know their auxiliary.compression.model setting is broken even
                # though compression succeeded.
                _aux_fail_model = getattr(self.context_compressor, "_last_aux_model_failure_model", None)
                _aux_fail_err = getattr(self.context_compressor, "_last_aux_model_failure_error", None)
                if _aux_fail_model:
                    # Dedup on (model, error) so we don't spam on every compaction
                    _aux_key = (_aux_fail_model, _aux_fail_err)
                    if getattr(self, "_last_aux_fallback_warning_key", None) != _aux_key:
                        self._last_aux_fallback_warning_key = _aux_key
                        self._emit_warning(
                            f"ℹ Configured compression model '{_aux_fail_model}' failed "
                            f"({_aux_fail_err or 'unknown error'}). Recovered using main model — "
                            "check auxiliary.compression.model in config.yaml."
                        )

            todo_snapshot = self._todo_store.format_for_injection()
            if todo_snapshot:
                compressed.append({"role": "user", "content": todo_snapshot})

            self._invalidate_system_prompt()
            new_system_prompt = self._build_system_prompt(system_message)
            self._cached_system_prompt = new_system_prompt

            if self._session_db:
                try:
                    # Propagate title to the new session with auto-numbering
                    old_title = self._session_db.get_session_title(self.session_id)
                    # Trigger memory extraction on the old session before it rotates.
                    self.commit_memory_session(messages)
                    self._session_db.end_session(self.session_id, "compression")
                    old_session_id = self.session_id
                    self.session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
                    # Update session_log_file to point to the new session's JSON file
                    self.session_log_file = self.logs_dir / f"session_{self.session_id}.json"
                    self._session_db.create_session(
                        session_id=self.session_id,
                        source=self.platform or os.environ.get("HERMES_SESSION_SOURCE", "cli"),
                        model=self.model,
                        parent_session_id=old_session_id,
                    )
                    # Auto-number the title for the continuation session
                    if old_title:
                        try:
                            new_title = self._session_db.get_next_title_in_lineage(old_title)
                            self._session_db.set_session_title(self.session_id, new_title)
                        except (ValueError, Exception) as e:
                            logger.debug("Could not propagate title on compression: %s", e)
                    self._session_db.update_system_prompt(self.session_id, new_system_prompt)
                    # Reset flush cursor — new session starts with no messages written
                    self._last_flushed_db_idx = 0
                except Exception as e:
                    logger.warning("Session DB compression split failed — new session will NOT be indexed: %s", e)

            # Notify the context engine that the session_id rotated because of
            # compression (not a fresh /new). Plugin engines (e.g. hermes-lcm) use
            # boundary_reason="compression" to preserve DAG lineage across the
            # rollover instead of re-initializing fresh per-session state.
            # See hermes-lcm#68. Built-in ContextCompressor ignores kwargs.
            try:
                _old_sid = locals().get("old_session_id")
                if _old_sid and hasattr(self.context_compressor, "on_session_start"):
                    self.context_compressor.on_session_start(
                        self.session_id or "",
                        boundary_reason="compression",
                        old_session_id=_old_sid,
                    )
            except Exception as _ce_err:
                logger.debug("context engine on_session_start (compression): %s", _ce_err)

            # Notify memory providers of the compression-driven session_id rotation
            # so provider-cached per-session state (Hindsight's _document_id,
            # accumulated turn buffers, counters) refreshes. reset=False because
            # the logical conversation continues; only the id and DB row rolled
            # over. See #6672.
            try:
                _old_sid = locals().get("old_session_id")
                if _old_sid and self._memory_manager:
                    self._memory_manager.on_session_switch(
                        self.session_id or "",
                        parent_session_id=_old_sid,
                        reset=False,
                        reason="compression",
                    )
            except Exception as _me_err:
                logger.debug("memory manager on_session_switch (compression): %s", _me_err)

            # Warn on repeated compressions (quality degrades with each pass)
            _cc = self.context_compressor.compression_count
            if _cc >= 2:
                self._vprint(
                    f"{self.log_prefix}⚠️  Session compressed {_cc} times — "
                    f"accuracy may degrade. Consider /new to start fresh.",
                    force=True,
                )

            # Update token estimate after compaction so pressure calculations
            # use the post-compression count, not the stale pre-compression one.
            _compressed_est = (
                estimate_tokens_rough(new_system_prompt)
                + estimate_messages_tokens_rough(compressed)
            )
            self.context_compressor.last_prompt_tokens = _compressed_est
            self.context_compressor.last_completion_tokens = 0

            # Clear the file-read dedup cache.  After compression the original
            # read content is summarised away — if the model re-reads the same
            # file it needs the full content, not a "file unchanged" stub.
            try:
                from tools.file_tools import reset_file_dedup
                reset_file_dedup(task_id)
            except Exception:
                pass

            logger.info(
                "context compression done: session=%s messages=%d->%d tokens=~%s",
                self.session_id or "none", _pre_msg_count, len(compressed),
                f"{_compressed_est:,}",
            )
            return compressed, new_system_prompt


    def _qwen_prepare_chat_messages(self, api_messages: list) -> list:
            prepared = copy.deepcopy(api_messages)
            if not prepared:
                return prepared

            for msg in prepared:
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if isinstance(content, str):
                    msg["content"] = [{"type": "text", "text": content}]
                elif isinstance(content, list):
                    # Normalize: convert bare strings to text dicts, keep dicts as-is.
                    # deepcopy already created independent copies, no need for dict().
                    normalized_parts = []
                    for part in content:
                        if isinstance(part, str):
                            normalized_parts.append({"type": "text", "text": part})
                        elif isinstance(part, dict):
                            normalized_parts.append(part)
                    if normalized_parts:
                        msg["content"] = normalized_parts

            # Inject cache_control on the last part of the system message.
            for msg in prepared:
                if isinstance(msg, dict) and msg.get("role") == "system":
                    content = msg.get("content")
                    if isinstance(content, list) and content and isinstance(content[-1], dict):
                        content[-1]["cache_control"] = {"type": "ephemeral"}
                    break

            return prepared


    def _qwen_prepare_chat_messages_inplace(self, messages: list) -> None:
            """In-place variant — mutates an already-copied message list."""
            if not messages:
                return

            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if isinstance(content, str):
                    msg["content"] = [{"type": "text", "text": content}]
                elif isinstance(content, list):
                    normalized_parts = []
                    for part in content:
                        if isinstance(part, str):
                            normalized_parts.append({"type": "text", "text": part})
                        elif isinstance(part, dict):
                            normalized_parts.append(part)
                    if normalized_parts:
                        msg["content"] = normalized_parts

            for msg in messages:
                if isinstance(msg, dict) and msg.get("role") == "system":
                    content = msg.get("content")
                    if isinstance(content, list) and content and isinstance(content[-1], dict):
                        content[-1]["cache_control"] = {"type": "ephemeral"}
                    break


    def _prepare_messages_for_non_vision_model(self, api_messages: list) -> list:
            """Strip native image parts when the active model lacks vision.

            Runs on the chat.completions / codex_responses paths. Vision-capable
            models pass through unchanged (provider and any downstream translator
            handle the image parts natively). Non-vision models get each image
            replaced by a cached vision_analyze text description so the turn
            doesn't fail with "model does not support image input".
            """
            if not any(
                isinstance(msg, dict) and self._content_has_image_parts(msg.get("content"))
                for msg in api_messages
            ):
                return api_messages

            if self._model_supports_vision():
                return api_messages

            transformed = copy.deepcopy(api_messages)
            for msg in transformed:
                if not isinstance(msg, dict):
                    continue
                # Reuse the Anthropic text-fallback preprocessor — the behaviour is
                # identical (walk content parts, replace images with cached
                # descriptions, merge back into a single text or structured
                # content). Naming is historical.
                msg["content"] = self._preprocess_anthropic_content(
                    msg.get("content"),
                    str(msg.get("role", "user") or "user"),
                )
            return transformed


    def _prepare_anthropic_messages_for_api(self, api_messages: list) -> list:
            # Fast exit when no message carries image content at all.
            if not any(
                isinstance(msg, dict) and self._content_has_image_parts(msg.get("content"))
                for msg in api_messages
            ):
                return api_messages

            # The Anthropic adapter (agent/anthropic_adapter.py:_convert_content_part_to_anthropic)
            # already translates OpenAI-style image_url/input_image parts into
            # native Anthropic ``{"type": "image", "source": ...}`` blocks. When
            # the active model supports vision we let the adapter do its job and
            # skip this legacy text-fallback preprocessor entirely.
            if self._model_supports_vision():
                return api_messages

            # Non-vision Anthropic model (rare today, but keep the fallback for
            # compat): replace each image part with a vision_analyze text note.
            transformed = copy.deepcopy(api_messages)
            for msg in transformed:
                if not isinstance(msg, dict):
                    continue
                msg["content"] = self._preprocess_anthropic_content(
                    msg.get("content"),
                    str(msg.get("role", "user") or "user"),
                )
            return transformed


    def _preprocess_anthropic_content(self, content: Any, role: str) -> Any:
            if not self._content_has_image_parts(content):
                return content

            text_parts: List[str] = []
            image_notes: List[str] = []
            for part in content:
                if isinstance(part, str):
                    if part.strip():
                        text_parts.append(part.strip())
                    continue
                if not isinstance(part, dict):
                    continue

                ptype = part.get("type")
                if ptype in {"text", "input_text"}:
                    text = str(part.get("text", "") or "").strip()
                    if text:
                        text_parts.append(text)
                    continue

                if ptype in {"image_url", "input_image"}:
                    image_data = part.get("image_url", {})
                    image_url = image_data.get("url", "") if isinstance(image_data, dict) else str(image_data or "")
                    if image_url:
                        image_notes.append(self._describe_image_for_anthropic_fallback(image_url, role))
                    else:
                        image_notes.append("[An image was attached but no image source was available.]")
                    continue

                text = str(part.get("text", "") or "").strip()
                if text:
                    text_parts.append(text)

            prefix = "\n\n".join(note for note in image_notes if note).strip()
            suffix = "\n".join(text for text in text_parts if text).strip()
            if prefix and suffix:
                return f"{prefix}\n\n{suffix}"
            if prefix:
                return prefix
            if suffix:
                return suffix
            return "[A multimodal message was converted to text for Anthropic compatibility.]"


    def _describe_image_for_anthropic_fallback(self, image_url: str, role: str) -> str:
            cache_key = hashlib.sha256(str(image_url or "").encode("utf-8")).hexdigest()
            cached = self._anthropic_image_fallback_cache.get(cache_key)
            if cached:
                return cached

            role_label = {
                "assistant": "assistant",
                "tool": "tool result",
            }.get(role, "user")
            analysis_prompt = (
                "Describe everything visible in this image in thorough detail. "
                "Include any text, code, UI, data, objects, people, layout, colors, "
                "and any other notable visual information."
            )

            vision_source = str(image_url or "")
            cleanup_path: Optional[Path] = None
            if vision_source.startswith("data:"):
                vision_source, cleanup_path = self._materialize_data_url_for_vision(vision_source)

            description = ""
            try:
                from tools.vision_tools import vision_analyze_tool

                result_json = asyncio.run(
                    vision_analyze_tool(image_url=vision_source, user_prompt=analysis_prompt)
                )
                result = json.loads(result_json) if isinstance(result_json, str) else {}
                description = (result.get("analysis") or "").strip()
            except Exception as e:
                description = f"Image analysis failed: {e}"
            finally:
                if cleanup_path and cleanup_path.exists():
                    try:
                        cleanup_path.unlink()
                    except OSError:
                        pass

            if not description:
                description = "Image analysis failed."

            note = f"[The {role_label} attached an image. Here's what it contains:\n{description}]"
            if vision_source and not str(image_url or "").startswith("data:"):
                note += (
                    f"\n[If you need a closer look, use vision_analyze with image_url: {vision_source}]"
                )

            self._anthropic_image_fallback_cache[cache_key] = note
            return note


    def _try_shrink_image_parts_in_messages(self, api_messages: list) -> bool:
            """Re-encode all native image parts at a smaller size to recover from
            image-too-large errors (Anthropic 5 MB, unknown other providers).

            Mutates ``api_messages`` in place. Returns True if any image part was
            actually replaced, False if there were no image parts to shrink or
            Pillow couldn't help (caller should surface the original error).

            Strategy: look for ``image_url`` / ``input_image`` parts carrying a
            ``data:image/...;base64,...`` payload.  For each one whose encoded
            size exceeds 4 MB (a safe target that slides under Anthropic's 5 MB
            ceiling with header overhead), write the base64 to a tempfile, call
            ``vision_tools._resize_image_for_vision`` to produce a smaller data
            URL, and substitute it in place.

            Non-data-URL images (http/https URLs) are not touched — the provider
            fetches those itself and the size limit is different.
            """
            if not api_messages:
                return False

            try:
                from tools.vision_tools import _resize_image_for_vision
            except Exception as exc:
                logger.warning("image-shrink recovery: vision_tools unavailable — %s", exc)
                return False

            # 4 MB target leaves comfortable headroom under Anthropic's 5 MB.
            # Non-Anthropic providers we haven't observed rejecting are fine with
            # much larger; shrinking to 4 MB here loses quality but only fires
            # after a confirmed provider rejection, so the alternative is failure.
            target_bytes = 4 * 1024 * 1024
            changed_count = 0

            def _shrink_data_url(url: str) -> Optional[str]:
                """Return a smaller data URL, or None if shrink can't help."""
                if not isinstance(url, str) or not url.startswith("data:"):
                    return None
                if len(url) <= target_bytes:
                    # This specific image wasn't the oversized one.
                    return None
                try:
                    header, _, data = url.partition(",")
                    mime = "image/jpeg"
                    if header.startswith("data:"):
                        mime_part = header[len("data:"):].split(";", 1)[0].strip()
                        if mime_part.startswith("image/"):
                            mime = mime_part
                    import base64 as _b64
                    raw = _b64.b64decode(data)
                    suffix = {
                        "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
                        "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/bmp": ".bmp",
                    }.get(mime, ".jpg")
                    tmp = tempfile.NamedTemporaryFile(
                        prefix="hermes_shrink_", suffix=suffix, delete=False,
                    )
                    try:
                        tmp.write(raw)
                        tmp.close()
                        resized = _resize_image_for_vision(
                            Path(tmp.name),
                            mime_type=mime,
                            max_base64_bytes=target_bytes,
                        )
                    finally:
                        try:
                            Path(tmp.name).unlink(missing_ok=True)
                        except Exception:
                            pass
                    if not resized or len(resized) >= len(url):
                        # Shrink didn't help (or made it bigger — corrupt input?).
                        return None
                    return resized
                except Exception as exc:
                    logger.warning("image-shrink recovery: re-encode failed — %s", exc)
                    return None

            for msg in api_messages:
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    ptype = part.get("type")
                    if ptype not in {"image_url", "input_image"}:
                        continue
                    image_value = part.get("image_url")
                    # OpenAI chat.completions: {"image_url": {"url": "data:..."}}
                    # OpenAI Responses: {"image_url": "data:..."}
                    if isinstance(image_value, dict):
                        url = image_value.get("url", "")
                        resized = _shrink_data_url(url)
                        if resized:
                            image_value["url"] = resized
                            changed_count += 1
                    elif isinstance(image_value, str):
                        resized = _shrink_data_url(image_value)
                        if resized:
                            part["image_url"] = resized
                            changed_count += 1

            if changed_count:
                logger.info(
                    "image-shrink recovery: re-encoded %d image part(s) to fit under %.0f MB",
                    changed_count, target_bytes / (1024 * 1024),
                )
            return changed_count > 0


    def _build_api_kwargs(self, api_messages: list) -> dict:
            """Build the keyword arguments dict for the active API mode."""
            if self.api_mode == "anthropic_messages":
                _transport = self._get_transport()
                anthropic_messages = self._prepare_anthropic_messages_for_api(api_messages)
                ctx_len = getattr(self, "context_compressor", None)
                ctx_len = ctx_len.context_length if ctx_len else None
                ephemeral_out = getattr(self, "_ephemeral_max_output_tokens", None)
                if ephemeral_out is not None:
                    self._ephemeral_max_output_tokens = None  # consume immediately
                return _transport.build_kwargs(
                    model=self.model,
                    messages=anthropic_messages,
                    tools=self.tools,
                    max_tokens=ephemeral_out if ephemeral_out is not None else self.max_tokens,
                    reasoning_config=self.reasoning_config,
                    is_oauth=self._is_anthropic_oauth,
                    preserve_dots=self._anthropic_preserve_dots(),
                    context_length=ctx_len,
                    base_url=getattr(self, "_anthropic_base_url", None),
                    fast_mode=(self.request_overrides or {}).get("speed") == "fast",
                    drop_context_1m_beta=bool(getattr(self, "_oauth_1m_beta_disabled", False)),
                )

            # AWS Bedrock native Converse API — bypasses the OpenAI client entirely.
            # The adapter handles message/tool conversion and boto3 calls directly.
            if self.api_mode == "bedrock_converse":
                _bt = self._get_transport()
                region = getattr(self, "_bedrock_region", None) or "us-east-1"
                guardrail = getattr(self, "_bedrock_guardrail_config", None)
                return _bt.build_kwargs(
                    model=self.model,
                    messages=api_messages,
                    tools=self.tools,
                    max_tokens=self.max_tokens or 4096,
                    region=region,
                    guardrail_config=guardrail,
                )

            if self.api_mode == "codex_responses":
                _ct = self._get_transport()
                is_github_responses = (
                    base_url_host_matches(self.base_url, "models.github.ai")
                    or base_url_host_matches(self.base_url, "api.githubcopilot.com")
                )
                is_codex_backend = (
                    self.provider == "openai-codex"
                    or (
                        self._base_url_hostname == "chatgpt.com"
                        and "/backend-api/codex" in self._base_url_lower
                    )
                )
                is_xai_responses = self.provider == "xai" or self._base_url_hostname == "api.x.ai"
                _msgs_for_codex = self._prepare_messages_for_non_vision_model(api_messages)
                return _ct.build_kwargs(
                    model=self.model,
                    messages=_msgs_for_codex,
                    tools=self.tools,
                    reasoning_config=self.reasoning_config,
                    session_id=getattr(self, "session_id", None),
                    max_tokens=self.max_tokens,
                    request_overrides=self.request_overrides,
                    is_github_responses=is_github_responses,
                    is_codex_backend=is_codex_backend,
                    is_xai_responses=is_xai_responses,
                    github_reasoning_extra=self._github_models_reasoning_extra_body() if is_github_responses else None,
                )

            # ── chat_completions (default) ─────────────────────────────────────
            _ct = self._get_transport()

            # Provider detection flags
            _is_qwen = self._is_qwen_portal()
            _is_or = self._is_openrouter_url()
            _is_gh = (
                base_url_host_matches(self._base_url_lower, "models.github.ai")
                or base_url_host_matches(self._base_url_lower, "api.githubcopilot.com")
            )
            _is_nous = "nousresearch" in self._base_url_lower
            _is_nvidia = "integrate.api.nvidia.com" in self._base_url_lower
            _is_kimi = (
                base_url_host_matches(self.base_url, "api.kimi.com")
                or base_url_host_matches(self.base_url, "moonshot.ai")
                or base_url_host_matches(self.base_url, "moonshot.cn")
            )
            _is_tokenhub = base_url_host_matches(self._base_url_lower, "tokenhub.tencentmaas.com")
            _is_lmstudio = (self.provider or "").strip().lower() == "lmstudio"

            # Temperature: _fixed_temperature_for_model may return OMIT_TEMPERATURE
            # sentinel (temperature omitted entirely), a numeric override, or None.
            try:
                from agent.auxiliary_client import _fixed_temperature_for_model, OMIT_TEMPERATURE
                _ft = _fixed_temperature_for_model(self.model, self.base_url)
                _omit_temp = _ft is OMIT_TEMPERATURE
                _fixed_temp = _ft if not _omit_temp else None
            except Exception:
                _omit_temp = False
                _fixed_temp = None

            # Provider preferences (OpenRouter-specific)
            _prefs: Dict[str, Any] = {}
            if self.providers_allowed:
                _prefs["only"] = self.providers_allowed
            if self.providers_ignored:
                _prefs["ignore"] = self.providers_ignored
            if self.providers_order:
                _prefs["order"] = self.providers_order
            if self.provider_sort:
                _prefs["sort"] = self.provider_sort
            if self.provider_require_parameters:
                _prefs["require_parameters"] = True
            if self.provider_data_collection:
                _prefs["data_collection"] = self.provider_data_collection

            # Anthropic max output for Claude on OpenRouter/Nous
            _ant_max = None
            if (_is_or or _is_nous) and "claude" in (self.model or "").lower():
                try:
                    from agent.anthropic_adapter import _get_anthropic_max_output
                    _ant_max = _get_anthropic_max_output(self.model)
                except Exception:
                    pass  # fail open — let the proxy pick its default

            # Qwen session metadata precomputed here (promptId is per-call random)
            _qwen_meta = None
            if _is_qwen:
                _qwen_meta = {
                    "sessionId": self.session_id or "hermes",
                    "promptId": str(uuid.uuid4()),
                }

            # Ephemeral max output override — consume immediately so the next
            # turn doesn't inherit it.
            _ephemeral_out = getattr(self, "_ephemeral_max_output_tokens", None)
            if _ephemeral_out is not None:
                self._ephemeral_max_output_tokens = None

            # Strip image parts for non-vision models (no-op when vision-capable).
            _msgs_for_chat = self._prepare_messages_for_non_vision_model(api_messages)

            return _ct.build_kwargs(
                model=self.model,
                messages=_msgs_for_chat,
                tools=self.tools,
                base_url=self.base_url,
                timeout=self._resolved_api_call_timeout(),
                max_tokens=self.max_tokens,
                ephemeral_max_output_tokens=_ephemeral_out,
                max_tokens_param_fn=self._max_tokens_param,
                reasoning_config=self.reasoning_config,
                request_overrides=self.request_overrides,
                session_id=getattr(self, "session_id", None),
                model_lower=(self.model or "").lower(),
                is_openrouter=_is_or,
                is_nous=_is_nous,
                is_qwen_portal=_is_qwen,
                is_github_models=_is_gh,
                is_nvidia_nim=_is_nvidia,
                is_kimi=_is_kimi,
                is_tokenhub=_is_tokenhub,
                is_lmstudio=_is_lmstudio,
                is_custom_provider=self.provider == "custom",
                ollama_num_ctx=self._ollama_num_ctx,
                provider_preferences=_prefs or None,
                qwen_prepare_fn=self._qwen_prepare_chat_messages if _is_qwen else None,
                qwen_prepare_inplace_fn=self._qwen_prepare_chat_messages_inplace if _is_qwen else None,
                qwen_session_metadata=_qwen_meta,
                fixed_temperature=_fixed_temp,
                omit_temperature=_omit_temp,
                supports_reasoning=self._supports_reasoning_extra_body(),
                github_reasoning_extra=self._github_models_reasoning_extra_body() if _is_gh else None,
                lmstudio_reasoning_options=self._lmstudio_reasoning_options_cached() if _is_lmstudio else None,
                anthropic_max_output=_ant_max,
                provider_name=self.provider,
            )


    def _build_assistant_message(self, assistant_message, finish_reason: str) -> dict:
            """Build a normalized assistant message dict from an API response message.

            Handles reasoning extraction, reasoning_details, and optional tool_calls
            so both the tool-call path and the final-response path share one builder.
            """
            assistant_tool_calls = getattr(assistant_message, "tool_calls", None)
            reasoning_text = self._extract_reasoning(assistant_message)
            _from_structured = bool(reasoning_text)

            # Fallback: extract inline <think> blocks from content when no structured
            # reasoning fields are present (some models/providers embed thinking
            # directly in the content rather than returning separate API fields).
            if not reasoning_text:
                content = assistant_message.content or ""
                think_blocks = re.findall(r'<think>(.*?)</think>', content, flags=re.DOTALL)
                if think_blocks:
                    combined = "\n\n".join(b.strip() for b in think_blocks if b.strip())
                    reasoning_text = combined or None

            if reasoning_text and self.verbose_logging:
                logging.debug(f"Captured reasoning ({len(reasoning_text)} chars): {reasoning_text}")

            if reasoning_text and self.reasoning_callback:
                # Skip callback when streaming is active — reasoning was already
                # displayed during the stream via one of two paths:
                #   (a) _fire_reasoning_delta (structured reasoning_content deltas)
                #   (b) _stream_delta tag extraction (<think>/<REASONING_SCRATCHPAD>)
                # When streaming is NOT active, always fire so non-streaming modes
                # (gateway, batch, quiet) still get reasoning.
                # Any reasoning that wasn't shown during streaming is caught by the
                # CLI post-response display fallback (cli.py _reasoning_shown_this_turn).
                if not self.stream_delta_callback and not self._stream_callback:
                    try:
                        self.reasoning_callback(reasoning_text)
                    except Exception:
                        pass

            # Sanitize surrogates from API response — some models (e.g. Kimi/GLM via Ollama)
            # can return invalid surrogate code points that crash json.dumps() on persist.
            _raw_content = assistant_message.content or ""
            _san_content = _sanitize_surrogates(_raw_content)
            if reasoning_text:
                reasoning_text = _sanitize_surrogates(reasoning_text)

            # Strip inline reasoning tags (<think>…</think> etc.) from the stored
            # assistant content.  Reasoning was already captured into
            # ``reasoning_text`` above (either from structured fields or the
            # inline-block fallback), so the raw tags in content are redundant.
            # Leaving them in place caused reasoning to leak to messaging
            # platforms (#8878, #9568), inflate context on subsequent turns
            # (#9306 observed 16% content-size reduction on a real MiniMax
            # session), and pollute generated session titles.  One strip at the
            # storage boundary cleans content for every downstream consumer:
            # API replay, session transcript, gateway delivery, CLI display,
            # compression, title generation.
            if isinstance(_san_content, str) and _san_content:
                _san_content = self._strip_think_blocks(_san_content).strip()

            msg = {
                "role": "assistant",
                "content": _san_content,
                "reasoning": reasoning_text,
                "finish_reason": finish_reason,
            }

            raw_reasoning_content = getattr(assistant_message, "reasoning_content", None)
            if raw_reasoning_content is None and hasattr(assistant_message, "model_extra"):
                model_extra = getattr(assistant_message, "model_extra", None) or {}
                if isinstance(model_extra, dict) and "reasoning_content" in model_extra:
                    raw_reasoning_content = model_extra["reasoning_content"]
            if raw_reasoning_content is not None:
                msg["reasoning_content"] = _sanitize_surrogates(raw_reasoning_content)
            elif assistant_tool_calls and self._needs_thinking_reasoning_pad():
                # DeepSeek v4 thinking mode and Kimi / Moonshot thinking mode
                # both require reasoning_content on every assistant tool-call
                # message. Without it, replaying the persisted message causes
                # HTTP 400 ("The reasoning_content in the thinking mode must
                # be passed back to the API"). Include streamed reasoning
                # text when captured; otherwise pad with empty string.
                # Refs #15250, #17400.
                msg["reasoning_content"] = reasoning_text or ""

            # Additive fallback (refs #16844, #16884). Streaming-only providers
            # (glm, MiniMax, gpt-5.x via aigw, Anthropic via openai-compat shims)
            # accumulate reasoning through ``delta.reasoning_content`` chunks
            # but never land it on the message object as a top-level attribute,
            # so neither branch above fires and the chain-of-thought is stored
            # only under the internal ``reasoning`` key. When the user later
            # replays that history through a DeepSeek-v4 / Kimi thinking model,
            # the missing ``reasoning_content`` causes HTTP 400 ("The
            # reasoning_content in the thinking mode must be passed back to the
            # API.").
            #
            # Promote the already-sanitized streamed ``reasoning_text`` to
            # ``reasoning_content`` at write time, but ONLY when no prior branch
            # already set it AND we actually captured reasoning text. This
            # preserves every existing behavior:
            #   - SDK-exposed ``reasoning_content`` (OpenAI/Moonshot/DeepSeek SDK)
            #     still wins.
            #   - DeepSeek tool-call ""-pad (#15250) still fires.
            #   - Non-thinking turns with no reasoning leave the field absent,
            #     so ``_copy_reasoning_content_for_api``'s cross-provider leak
            #     guard (#15748) and ``reasoning``→``reasoning_content``
            #     promotion tiers still apply at replay time.
            if "reasoning_content" not in msg and reasoning_text:
                msg["reasoning_content"] = reasoning_text

            if hasattr(assistant_message, 'reasoning_details') and assistant_message.reasoning_details:
                # Pass reasoning_details back unmodified so providers (OpenRouter,
                # Anthropic, OpenAI) can maintain reasoning continuity across turns.
                # Each provider may include opaque fields (signature, encrypted_content)
                # that must be preserved exactly.
                raw_details = assistant_message.reasoning_details
                preserved = []
                for d in raw_details:
                    if isinstance(d, dict):
                        preserved.append(d)
                    elif hasattr(d, "__dict__"):
                        preserved.append(d.__dict__)
                    elif hasattr(d, "model_dump"):
                        preserved.append(d.model_dump())
                if preserved:
                    msg["reasoning_details"] = preserved

            # Codex Responses API: preserve encrypted reasoning items for
            # multi-turn continuity. These get replayed as input on the next turn.
            codex_items = getattr(assistant_message, "codex_reasoning_items", None)
            if codex_items:
                msg["codex_reasoning_items"] = codex_items

            # Codex Responses API: preserve exact assistant message items (with
            # id/phase) so follow-up turns can replay structured items instead of
            # flattening to plain text. This is required for prefix cache hits.
            codex_message_items = getattr(assistant_message, "codex_message_items", None)
            if codex_message_items:
                msg["codex_message_items"] = codex_message_items

            if assistant_tool_calls:
                tool_calls = []
                for tool_call in assistant_tool_calls:
                    raw_id = getattr(tool_call, "id", None)
                    call_id = getattr(tool_call, "call_id", None)
                    if not isinstance(call_id, str) or not call_id.strip():
                        embedded_call_id, _ = self._split_responses_tool_id(raw_id)
                        call_id = embedded_call_id
                    if not isinstance(call_id, str) or not call_id.strip():
                        if isinstance(raw_id, str) and raw_id.strip():
                            call_id = raw_id.strip()
                        else:
                            _fn = getattr(tool_call, "function", None)
                            _fn_name = getattr(_fn, "name", "") if _fn else ""
                            _fn_args = getattr(_fn, "arguments", "{}") if _fn else "{}"
                            call_id = self._deterministic_call_id(_fn_name, _fn_args, len(tool_calls))
                    call_id = call_id.strip()

                    response_item_id = getattr(tool_call, "response_item_id", None)
                    if not isinstance(response_item_id, str) or not response_item_id.strip():
                        _, embedded_response_item_id = self._split_responses_tool_id(raw_id)
                        response_item_id = embedded_response_item_id

                    response_item_id = self._derive_responses_function_call_id(
                        call_id,
                        response_item_id if isinstance(response_item_id, str) else None,
                    )

                    tc_dict = {
                        "id": call_id,
                        "call_id": call_id,
                        "response_item_id": response_item_id,
                        "type": tool_call.type,
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        },
                    }
                    # Preserve extra_content (e.g. Gemini thought_signature) so it
                    # is sent back on subsequent API calls.  Without this, Gemini 3
                    # thinking models reject the request with a 400 error.
                    extra = getattr(tool_call, "extra_content", None)
                    if extra is not None:
                        if hasattr(extra, "model_dump"):
                            extra = extra.model_dump()
                        tc_dict["extra_content"] = extra
                    tool_calls.append(tc_dict)
                msg["tool_calls"] = tool_calls

            return msg


    def _copy_reasoning_content_for_api(self, source_msg: dict, api_msg: dict) -> None:
            """Copy provider-facing reasoning fields onto an API replay message."""
            if source_msg.get("role") != "assistant":
                return

            # 1. Explicit reasoning_content already set — preserve it verbatim
            # (includes DeepSeek/Kimi's own empty-string placeholder written at
            # creation time, and any valid reasoning content from the same provider).
            existing = source_msg.get("reasoning_content")
            if isinstance(existing, str):
                api_msg["reasoning_content"] = existing
                return

            needs_thinking_pad = self._needs_thinking_reasoning_pad()

            # 2. Cross-provider poisoned history (#15748): on DeepSeek/Kimi,
            # if the source turn has tool_calls AND a 'reasoning' field but no
            # 'reasoning_content' key, the 'reasoning' text was written by a
            # prior provider (e.g. MiniMax) — DeepSeek's own _build_assistant_message
            # pins reasoning_content at creation time for tool-call turns, so the
            # shape (reasoning set, reasoning_content absent, tool_calls present)
            # is unreachable from same-provider DeepSeek history after this fix.
            # Inject "" to satisfy the API without leaking another provider's
            # chain of thought to DeepSeek/Kimi.
            normalized_reasoning = source_msg.get("reasoning")
            if (
                needs_thinking_pad
                and source_msg.get("tool_calls")
                and isinstance(normalized_reasoning, str)
                and normalized_reasoning
            ):
                api_msg["reasoning_content"] = ""
                return

            # 3. Healthy session: promote 'reasoning' field to 'reasoning_content'
            # for providers that use the internal 'reasoning' key.
            # This must happen before the unconditional empty-string fallback so
            # genuine reasoning content is not overwritten (#15812 regression in
            # PR #15478).
            if isinstance(normalized_reasoning, str) and normalized_reasoning:
                api_msg["reasoning_content"] = normalized_reasoning
                return

            # 4. DeepSeek / Kimi thinking mode: all assistant messages need
            # reasoning_content. Inject "" to satisfy the provider's requirement
            # when no explicit reasoning content is present. Covers both
            # tool-call turns (already-poisoned history with no reasoning at all)
            # and plain text turns.
            if needs_thinking_pad:
                api_msg["reasoning_content"] = ""
                return

            # 5. reasoning_content was present but not a string (e.g. None after
            # context compaction).  Don't pass null to the API.
            api_msg.pop("reasoning_content", None)


    def _needs_thinking_reasoning_pad(self) -> bool:
            """Return True when the active provider enforces reasoning_content echo-back.

            DeepSeek v4 thinking and Kimi / Moonshot thinking both reject replays
            of assistant tool-call messages that omit ``reasoning_content`` (refs
            #15250, #17400).
            """
            return (
                self._needs_deepseek_tool_reasoning()
                or self._needs_kimi_tool_reasoning()
            )


    def _needs_kimi_tool_reasoning(self) -> bool:
            """Return True when the current provider is Kimi / Moonshot thinking mode.

            Kimi ``/coding`` and Moonshot thinking mode both require
            ``reasoning_content`` on every assistant tool-call message; omitting
            it causes the next replay to fail with HTTP 400.
            """
            return (
                self.provider in {"kimi-coding", "kimi-coding-cn"}
                or base_url_host_matches(self.base_url, "api.kimi.com")
                or base_url_host_matches(self.base_url, "moonshot.ai")
                or base_url_host_matches(self.base_url, "moonshot.cn")
            )


    def _needs_deepseek_tool_reasoning(self) -> bool:
            """Return True when the current provider is DeepSeek thinking mode.

            DeepSeek V4 thinking mode requires ``reasoning_content`` on every
            assistant tool-call turn; omitting it causes HTTP 400 when the
            message is replayed in a subsequent API request (#15250).
            """
            provider = (self.provider or "").lower()
            model = (self.model or "").lower()
            return (
                provider == "deepseek"
                or "deepseek" in model
                or base_url_host_matches(self.base_url, "api.deepseek.com")
            )


    def _supports_reasoning_extra_body(self) -> bool:
            """Return True when reasoning extra_body is safe to send for this route/model.

            OpenRouter forwards unknown extra_body fields to upstream providers.
            Some providers/routes reject `reasoning` with 400s, so gate it to
            known reasoning-capable model families and direct Nous Portal.
            """
            if base_url_host_matches(self._base_url_lower, "nousresearch.com"):
                return True
            if base_url_host_matches(self._base_url_lower, "ai-gateway.vercel.sh"):
                return True
            if (
                base_url_host_matches(self._base_url_lower, "models.github.ai")
                or base_url_host_matches(self._base_url_lower, "api.githubcopilot.com")
            ):
                try:
                    from hermes_cli.models import github_model_reasoning_efforts

                    return bool(github_model_reasoning_efforts(self.model))
                except Exception:
                    return False
            if (self.provider or "").strip().lower() == "lmstudio":
                opts = self._lmstudio_reasoning_options_cached()
                # "off-only" (or absent) means no real reasoning capability.
                return any(opt and opt != "off" for opt in opts)
            if "openrouter" not in self._base_url_lower:
                return False
            if "api.mistral.ai" in self._base_url_lower:
                return False

            model = (self.model or "").lower()
            reasoning_model_prefixes = (
                "deepseek/",
                "anthropic/",
                "openai/",
                "x-ai/",
                "google/gemini-2",
                "qwen/qwen3",
                "tencent/hy3-preview",
            )
            return any(model.startswith(prefix) for prefix in reasoning_model_prefixes)


    def _lmstudio_reasoning_options_cached(self) -> list[str]:
            """Probe LM Studio's published reasoning ``allowed_options`` once per
            (model, base_url). The list (e.g. ``["off","on"]`` or
            ``["off","minimal","low"]``) is needed both for the supports-reasoning
            gate and for clamping the emitted ``reasoning_effort`` so toggle-style
            models don't 400 on ``high``. Cache is keyed on (model, base_url) so
            ``/model`` swaps and base-URL changes don't reuse a stale list.
            Non-empty results are cached permanently (model capabilities don't
            change). Empty results (transient probe failure OR genuinely
            non-reasoning model) are cached with a 60-second TTL to avoid an
            HTTP round-trip on every turn while still retrying reasonably soon.
            """
            import time as _time

            cache = getattr(self, "_lm_reasoning_opts_cache", None)
            if cache is None:
                cache = self._lm_reasoning_opts_cache = {}
            key = (self.model, self.base_url)
            cached = cache.get(key)
            if cached is not None:
                opts, ts = cached
                # Non-empty → permanent. Empty → 60s TTL.
                if opts or (_time.monotonic() - ts) < 60:
                    return opts
            try:
                from hermes_cli.models import lmstudio_model_reasoning_options
                opts = lmstudio_model_reasoning_options(
                    self.model, self.base_url, getattr(self, "api_key", ""),
                )
            except Exception:
                opts = []
            cache[key] = (opts, _time.monotonic())
            return opts


    def _resolve_lmstudio_summary_reasoning_effort(self) -> Optional[str]:
            """Resolve a safe top-level ``reasoning_effort`` for LM Studio.

            The iteration-limit summary path calls ``chat.completions.create()``
            directly, bypassing the transport. Share the helper so the two paths
            can't drift on effort resolution and clamping.
            """
            from agent.lmstudio_reasoning import resolve_lmstudio_effort
            return resolve_lmstudio_effort(
                self.reasoning_config,
                self._lmstudio_reasoning_options_cached(),
            )


    def _github_models_reasoning_extra_body(self) -> dict | None:
            """Format reasoning payload for GitHub Models/OpenAI-compatible routes."""
            try:
                from hermes_cli.models import github_model_reasoning_efforts
            except Exception:
                return None

            supported_efforts = github_model_reasoning_efforts(self.model)
            if not supported_efforts:
                return None

            if self.reasoning_config and isinstance(self.reasoning_config, dict):
                if self.reasoning_config.get("enabled") is False:
                    return None
                requested_effort = str(
                    self.reasoning_config.get("effort", "medium")
                ).strip().lower()
            else:
                requested_effort = "medium"

            if requested_effort == "xhigh" and "high" in supported_efforts:
                requested_effort = "high"
            elif requested_effort not in supported_efforts:
                if requested_effort == "minimal" and "low" in supported_efforts:
                    requested_effort = "low"
                elif "medium" in supported_efforts:
                    requested_effort = "medium"
                else:
                    requested_effort = supported_efforts[0]

            return {"effort": requested_effort}


