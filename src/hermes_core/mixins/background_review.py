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

class BackgroundReviewMixin:
    def _spawn_background_review(
            self,
            messages_snapshot: List[Dict],
            review_memory: bool = False,
            review_skills: bool = False,
        ) -> None:
            """Spawn a background thread to review the conversation for memory/skill saves.

            Creates a full AIAgent fork with the same model, tools, and context as the
            main session. The review prompt is appended as the next user turn in the
            forked conversation. Writes directly to the shared memory/skill stores.
            Never modifies the main conversation history or produces user-visible output.
            """
            import threading

            # Pick the right prompt based on which triggers fired
            if review_memory and review_skills:
                prompt = self._COMBINED_REVIEW_PROMPT
            elif review_memory:
                prompt = self._MEMORY_REVIEW_PROMPT
            else:
                prompt = self._SKILL_REVIEW_PROMPT

            def _run_review():
                import contextlib
                # Install a non-interactive approval callback on this worker
                # thread so any dangerous-command guard the review agent trips
                # resolves to "deny" instead of falling back to input() -- which
                # deadlocks against the parent's prompt_toolkit TUI (#15216).
                # Same pattern as _subagent_auto_deny in tools/delegate_tool.py.
                def _bg_review_auto_deny(command, description, **kwargs):
                    logger.warning(
                        "Background review auto-denied dangerous command: %s (%s)",
                        command, description,
                    )
                    return "deny"
                try:
                    _set_approval_callback(_bg_review_auto_deny)
                except Exception:
                    pass
                review_agent = None
                try:
                    with open(os.devnull, "w") as _devnull, \
                         contextlib.redirect_stdout(_devnull), \
                         contextlib.redirect_stderr(_devnull):
                        # Inherit the parent agent's live runtime (provider, model,
                        # base_url, api_key, api_mode) so the fork uses the exact
                        # same credentials the main turn is using.  Without this,
                        # AIAgent.__init__ re-runs auto-resolution from env vars,
                        # which fails for OAuth-only providers, session-scoped
                        # creds, or credential-pool setups where the resolver can't
                        # reconstruct auth from scratch -- producing the spurious
                        # "No LLM provider configured" warning at end of turn.
                        _parent_runtime = self._current_main_runtime()
                        review_agent = AIAgent(
                            model=self.model,
                            max_iterations=8,
                            quiet_mode=True,
                            platform=self.platform,
                            provider=self.provider,
                            api_mode=_parent_runtime.get("api_mode") or None,
                            base_url=_parent_runtime.get("base_url") or None,
                            api_key=_parent_runtime.get("api_key") or None,
                            credential_pool=getattr(self, "_credential_pool", None),
                            parent_session_id=self.session_id,
                            enabled_toolsets=["memory", "skills"],
                        )
                        review_agent._memory_write_origin = "background_review"
                        review_agent._memory_write_context = "background_review"
                        review_agent._memory_store = self._memory_store
                        review_agent._memory_enabled = self._memory_enabled
                        review_agent._user_profile_enabled = self._user_profile_enabled
                        review_agent._memory_nudge_interval = 0
                        review_agent._skill_nudge_interval = 0

                        review_agent.run_conversation(
                            user_message=prompt,
                            conversation_history=messages_snapshot,
                        )

                    # Scan the review agent's messages for successful tool actions
                    # and surface a compact summary to the user. Tool messages
                    # already present in messages_snapshot must be skipped, since
                    # the review agent inherits that history and would otherwise
                    # re-surface stale "created"/"updated" messages from the prior
                    # conversation as if they just happened (issue #14944).
                    actions = self._summarize_background_review_actions(
                        getattr(review_agent, "_session_messages", []),
                        messages_snapshot,
                    )

                    if actions:
                        summary = " · ".join(dict.fromkeys(actions))
                        self._safe_print(
                            f"  💾 Self-improvement review: {summary}"
                        )
                        _bg_cb = self.background_review_callback
                        if _bg_cb:
                            try:
                                _bg_cb(
                                    f"💾 Self-improvement review: {summary}"
                                )
                            except Exception:
                                pass

                except Exception as e:
                    logger.warning("Background memory/skill review failed: %s", e)
                    self._emit_auxiliary_failure("background review", e)
                finally:
                    # Background review agents can initialize memory providers
                    # (for example Hindsight) that own their own network clients.
                    # Explicitly stop those providers before closing the agent so
                    # their aiohttp sessions do not leak until GC/process exit.
                    # Then close all remaining resources (httpx client,
                    # subprocesses, etc.) so GC doesn't try to clean them up on a
                    # dead asyncio event loop (which produces "Event loop is
                    # closed" errors).
                    if review_agent is not None:
                        try:
                            review_agent.shutdown_memory_provider()
                        except Exception:
                            pass
                        try:
                            review_agent.close()
                        except Exception:
                            pass
                    # Clear the approval callback on this bg-review thread so a
                    # recycled thread-id doesn't inherit a stale reference.
                    try:
                        _set_approval_callback(None)
                    except Exception:
                        pass

            t = threading.Thread(target=_run_review, daemon=True, name="bg-review")
            t.start()


    def _summarize_background_review_actions(
            review_messages: List[Dict],
            prior_snapshot: List[Dict],
        ) -> List[str]:
            """Build the human-facing action summary for a background review pass.

            Walks the review agent's session messages and collects "successful tool
            action" descriptions to surface to the user (e.g. "Memory updated").
            Tool messages already present in ``prior_snapshot`` are skipped so we
            don't re-surface stale results from the prior conversation that the
            review agent inherited via ``conversation_history`` (issue #14944).

            Matching is by ``tool_call_id`` when available, with a content-equality
            fallback for tool messages that lack one.
            """
            existing_tool_call_ids = set()
            existing_tool_contents = set()
            for prior in prior_snapshot or []:
                if not isinstance(prior, dict) or prior.get("role") != "tool":
                    continue
                tcid = prior.get("tool_call_id")
                if tcid:
                    existing_tool_call_ids.add(tcid)
                else:
                    content = prior.get("content")
                    if isinstance(content, str):
                        existing_tool_contents.add(content)

            actions: List[str] = []
            for msg in review_messages or []:
                if not isinstance(msg, dict) or msg.get("role") != "tool":
                    continue
                tcid = msg.get("tool_call_id")
                if tcid and tcid in existing_tool_call_ids:
                    continue
                if not tcid:
                    content_str = msg.get("content")
                    if isinstance(content_str, str) and content_str in existing_tool_contents:
                        continue
                try:
                    data = json.loads(msg.get("content", "{}"))
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(data, dict) or not data.get("success"):
                    continue
                message = data.get("message", "")
                target = data.get("target", "")
                if "created" in message.lower():
                    actions.append(message)
                elif "updated" in message.lower():
                    actions.append(message)
                elif "added" in message.lower() or (target and "add" in message.lower()):
                    label = "Memory" if target == "memory" else "User profile" if target == "user" else target
                    actions.append(f"{label} updated")
                elif "Entry added" in message:
                    label = "Memory" if target == "memory" else "User profile" if target == "user" else target
                    actions.append(f"{label} updated")
                elif "removed" in message.lower() or "replaced" in message.lower():
                    label = "Memory" if target == "memory" else "User profile" if target == "user" else target
                    actions.append(f"{label} updated")
            return actions


