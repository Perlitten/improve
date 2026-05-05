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

class SessionHistoryMixin:
    def _build_memory_write_metadata(
            self,
            *,
            write_origin: Optional[str] = None,
            execution_context: Optional[str] = None,
            task_id: Optional[str] = None,
            tool_call_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            """Build provenance metadata for external memory-provider mirrors."""
            metadata: Dict[str, Any] = {
                "write_origin": write_origin or getattr(self, "_memory_write_origin", "assistant_tool"),
                "execution_context": (
                    execution_context
                    or getattr(self, "_memory_write_context", "foreground")
                ),
                "session_id": self.session_id or "",
                "parent_session_id": self._parent_session_id or "",
                "platform": self.platform or os.environ.get("HERMES_SESSION_SOURCE", "cli"),
                "tool_name": "memory",
            }
            if task_id:
                metadata["task_id"] = task_id
            if tool_call_id:
                metadata["tool_call_id"] = tool_call_id
            return {k: v for k, v in metadata.items() if v not in (None, "")}


    def _apply_persist_user_message_override(self, messages: List[Dict]) -> None:
            """Rewrite the current-turn user message before persistence/return.

            Some call paths need an API-only user-message variant without letting
            that synthetic text leak into persisted transcripts or resumed session
            history. When an override is configured for the active turn, mutate the
            in-memory messages list in place so both persistence and returned
            history stay clean.
            """
            idx = getattr(self, "_persist_user_message_idx", None)
            override = getattr(self, "_persist_user_message_override", None)
            if override is None or idx is None:
                return
            if 0 <= idx < len(messages):
                msg = messages[idx]
                if isinstance(msg, dict) and msg.get("role") == "user":
                    msg["content"] = override


    def _persist_session(self, messages: List[Dict], conversation_history: List[Dict] = None):
            """Save session state to both JSON log and SQLite on any exit path.

            Ensures conversations are never lost, even on errors or early returns.
            """
            self._apply_persist_user_message_override(messages)
            self._session_messages = messages
            self._save_session_log(messages)
            self._flush_messages_to_session_db(messages, conversation_history)


    def _flush_messages_to_session_db(self, messages: List[Dict], conversation_history: List[Dict] = None):
            """Persist any un-flushed messages to the SQLite session store.

            Uses _last_flushed_db_idx to track which messages have already been
            written, so repeated calls (from multiple exit paths) only write
            truly new messages — preventing the duplicate-write bug (#860).
            """
            if not self._session_db:
                return
            self._apply_persist_user_message_override(messages)
            try:
                # If create_session() failed at startup (e.g. transient lock), the
                # session row may not exist yet.  ensure_session() uses INSERT OR
                # IGNORE so it is a no-op when the row is already there.
                self._session_db.ensure_session(
                    self.session_id,
                    source=self.platform or "cli",
                    model=self.model,
                )
                start_idx = len(conversation_history) if conversation_history else 0
                flush_from = max(start_idx, self._last_flushed_db_idx)
                for msg in messages[flush_from:]:
                    role = msg.get("role", "unknown")
                    content = msg.get("content")
                    tool_calls_data = None
                    if hasattr(msg, "tool_calls") and isinstance(msg.tool_calls, list) and msg.tool_calls:
                        tool_calls_data = [
                            {"name": tc.function.name, "arguments": tc.function.arguments}
                            for tc in msg.tool_calls
                        ]
                    elif isinstance(msg.get("tool_calls"), list):
                        tool_calls_data = msg["tool_calls"]
                    self._session_db.append_message(
                        session_id=self.session_id,
                        role=role,
                        content=content,
                        tool_name=msg.get("tool_name"),
                        tool_calls=tool_calls_data,
                        tool_call_id=msg.get("tool_call_id"),
                        finish_reason=msg.get("finish_reason"),
                        reasoning=msg.get("reasoning") if role == "assistant" else None,
                        reasoning_content=msg.get("reasoning_content") if role == "assistant" else None,
                        reasoning_details=msg.get("reasoning_details") if role == "assistant" else None,
                        codex_reasoning_items=msg.get("codex_reasoning_items") if role == "assistant" else None,
                        codex_message_items=msg.get("codex_message_items") if role == "assistant" else None,
                    )
                self._last_flushed_db_idx = len(messages)
            except Exception as e:
                logger.warning("Session DB append_message failed: %s", e)


    def _get_messages_up_to_last_assistant(self, messages: List[Dict]) -> List[Dict]:
            """
            Get messages up to (but not including) the last assistant turn.

            This is used when we need to "roll back" to the last successful point
            in the conversation, typically when the final assistant message is
            incomplete or malformed.

            Args:
                messages: Full message list

            Returns:
                Messages up to the last complete assistant turn (ending with user/tool message)
            """
            if not messages:
                return []

            # Find the index of the last assistant message
            last_assistant_idx = None
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "assistant":
                    last_assistant_idx = i
                    break

            if last_assistant_idx is None:
                # No assistant message found, return all messages
                return messages.copy()

            # Return everything up to (not including) the last assistant message
            return messages[:last_assistant_idx]


    def _convert_to_trajectory_format(self, messages: List[Dict[str, Any]], user_query: str, completed: bool) -> List[Dict[str, Any]]:
            """
            Convert internal message format to trajectory format for saving.

            Args:
                messages (List[Dict]): Internal message history
                user_query (str): Original user query
                completed (bool): Whether the conversation completed successfully

            Returns:
                List[Dict]: Messages in trajectory format
            """
            trajectory = []

            # Add system message with tool definitions
            system_msg = (
                "You are a function calling AI model. You are provided with function signatures within <tools> </tools> XML tags. "
                "You may call one or more functions to assist with the user query. If available tools are not relevant in assisting "
                "with user query, just respond in natural conversational language. Don't make assumptions about what values to plug "
                "into functions. After calling & executing the functions, you will be provided with function results within "
                "<tool_response> </tool_response> XML tags. Here are the available tools:\n"
                f"<tools>\n{self._format_tools_for_system_message()}\n</tools>\n"
                "For each function call return a JSON object, with the following pydantic model json schema for each:\n"
                "{'title': 'FunctionCall', 'type': 'object', 'properties': {'name': {'title': 'Name', 'type': 'string'}, "
                "'arguments': {'title': 'Arguments', 'type': 'object'}}, 'required': ['name', 'arguments']}\n"
                "Each function call should be enclosed within <tool_call> </tool_call> XML tags.\n"
                "Example:\n<tool_call>\n{'name': <function-name>,'arguments': <args-dict>}\n</tool_call>"
            )

            trajectory.append({
                "from": "system",
                "value": system_msg
            })

            # Add the actual user prompt (from the dataset) as the first human message
            trajectory.append({
                "from": "human",
                "value": user_query
            })

            # Skip the first message (the user query) since we already added it above.
            # Prefill messages are injected at API-call time only (not in the messages
            # list), so no offset adjustment is needed here.
            i = 1

            while i < len(messages):
                msg = messages[i]

                if msg["role"] == "assistant":
                    # Check if this message has tool calls
                    if "tool_calls" in msg and msg["tool_calls"]:
                        # Format assistant message with tool calls
                        # Add <think> tags around reasoning for trajectory storage
                        content = ""

                        # Prepend reasoning in <think> tags if available (native thinking tokens)
                        if msg.get("reasoning") and msg["reasoning"].strip():
                            content = f"<think>\n{msg['reasoning']}\n</think>\n"

                        if msg.get("content") and msg["content"].strip():
                            # Convert any <REASONING_SCRATCHPAD> tags to <think> tags
                            # (used when native thinking is disabled and model reasons via XML)
                            content += convert_scratchpad_to_think(msg["content"]) + "\n"

                        # Add tool calls wrapped in XML tags
                        for tool_call in msg["tool_calls"]:
                            if not tool_call or not isinstance(tool_call, dict): continue
                            # Parse arguments - should always succeed since we validate during conversation
                            # but keep try-except as safety net
                            try:
                                arguments = json.loads(tool_call["function"]["arguments"]) if isinstance(tool_call["function"]["arguments"], str) else tool_call["function"]["arguments"]
                            except json.JSONDecodeError:
                                # This shouldn't happen since we validate and retry during conversation,
                                # but if it does, log warning and use empty dict
                                logging.warning(f"Unexpected invalid JSON in trajectory conversion: {tool_call['function']['arguments'][:100]}")
                                arguments = {}

                            tool_call_json = {
                                "name": tool_call["function"]["name"],
                                "arguments": arguments
                            }
                            content += f"<tool_call>\n{json.dumps(tool_call_json, ensure_ascii=False)}\n</tool_call>\n"

                        # Ensure every gpt turn has a <think> block (empty if no reasoning)
                        # so the format is consistent for training data
                        if "<think>" not in content:
                            content = "<think>\n</think>\n" + content

                        trajectory.append({
                            "from": "gpt",
                            "value": content.rstrip()
                        })

                        # Collect all subsequent tool responses
                        tool_responses = []
                        j = i + 1
                        while j < len(messages) and messages[j]["role"] == "tool":
                            tool_msg = messages[j]
                            # Format tool response with XML tags
                            tool_response = "<tool_response>\n"

                            # Try to parse tool content as JSON if it looks like JSON
                            tool_content = tool_msg["content"]
                            try:
                                if tool_content.strip().startswith(("{", "[")):
                                    tool_content = json.loads(tool_content)
                            except (json.JSONDecodeError, AttributeError):
                                pass  # Keep as string if not valid JSON

                            tool_index = len(tool_responses)
                            tool_name = (
                                msg["tool_calls"][tool_index]["function"]["name"]
                                if tool_index < len(msg["tool_calls"])
                                else "unknown"
                            )
                            tool_response += json.dumps({
                                "tool_call_id": tool_msg.get("tool_call_id", ""),
                                "name": tool_name,
                                "content": tool_content
                            }, ensure_ascii=False)
                            tool_response += "\n</tool_response>"
                            tool_responses.append(tool_response)
                            j += 1

                        # Add all tool responses as a single message
                        if tool_responses:
                            trajectory.append({
                                "from": "tool",
                                "value": "\n".join(tool_responses)
                            })
                            i = j - 1  # Skip the tool messages we just processed

                    else:
                        # Regular assistant message without tool calls
                        # Add <think> tags around reasoning for trajectory storage
                        content = ""

                        # Prepend reasoning in <think> tags if available (native thinking tokens)
                        if msg.get("reasoning") and msg["reasoning"].strip():
                            content = f"<think>\n{msg['reasoning']}\n</think>\n"

                        # Convert any <REASONING_SCRATCHPAD> tags to <think> tags
                        # (used when native thinking is disabled and model reasons via XML)
                        raw_content = msg["content"] or ""
                        content += convert_scratchpad_to_think(raw_content)

                        # Ensure every gpt turn has a <think> block (empty if no reasoning)
                        if "<think>" not in content:
                            content = "<think>\n</think>\n" + content

                        trajectory.append({
                            "from": "gpt",
                            "value": content.strip()
                        })

                elif msg["role"] == "user":
                    trajectory.append({
                        "from": "human",
                        "value": msg["content"]
                    })

                i += 1

            return trajectory


    def _save_trajectory(self, messages: List[Dict[str, Any]], user_query: str, completed: bool):
            """
            Save conversation trajectory to JSONL file.

            Args:
                messages (List[Dict]): Complete message history
                user_query (str): Original user query
                completed (bool): Whether the conversation completed successfully
            """
            if not self.save_trajectories:
                return

            trajectory = self._convert_to_trajectory_format(messages, user_query, completed)
            _save_trajectory_to_file(trajectory, self.model, completed)


    def _clean_session_content(content: str) -> str:
            """Convert REASONING_SCRATCHPAD to think tags and clean up whitespace."""
            if not content:
                return content
            content = convert_scratchpad_to_think(content)
            content = re.sub(r'\n+(<think>)', r'\n\1', content)
            content = re.sub(r'(</think>)\n+', r'\1\n', content)
            return content.strip()


    def _save_session_log(self, messages: List[Dict[str, Any]] = None):
            """
            Save the full raw session to a JSON file.

            Stores every message exactly as the agent sees it: user messages,
            assistant messages (with reasoning, finish_reason, tool_calls),
            tool responses (with tool_call_id, tool_name), and injected system
            messages (compression summaries, todo snapshots, etc.).

            REASONING_SCRATCHPAD tags are converted to <think> blocks for consistency.
            Overwritten after each turn so it always reflects the latest state.
            """
            messages = messages or self._session_messages
            if not messages:
                return

            try:
                # Clean assistant content for session logs
                cleaned = []
                for msg in messages:
                    if msg.get("role") == "assistant" and msg.get("content"):
                        msg = dict(msg)
                        msg["content"] = self._clean_session_content(msg["content"])
                    cleaned.append(msg)

                # Guard: never overwrite a larger session log with fewer messages.
                # This protects against data loss when --resume loads a session whose
                # messages weren't fully written to SQLite — the resumed agent starts
                # with partial history and would otherwise clobber the full JSON log.
                if self.session_log_file.exists():
                    try:
                        existing = json.loads(self.session_log_file.read_text(encoding="utf-8"))
                        existing_count = existing.get("message_count", len(existing.get("messages", [])))
                        if existing_count > len(cleaned):
                            logging.debug(
                                "Skipping session log overwrite: existing has %d messages, current has %d",
                                existing_count, len(cleaned),
                            )
                            return
                    except Exception:
                        pass  # corrupted existing file — allow the overwrite

                entry = {
                    "session_id": self.session_id,
                    "model": self.model,
                    "base_url": self.base_url,
                    "platform": self.platform,
                    "session_start": self.session_start.isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "system_prompt": self._cached_system_prompt or "",
                    "tools": self.tools or [],
                    "message_count": len(cleaned),
                    "messages": cleaned,
                }

                atomic_json_write(
                    self.session_log_file,
                    entry,
                    indent=2,
                    default=str,
                )

            except Exception as e:
                if self.verbose_logging:
                    logging.warning(f"Failed to save session log: {e}")


    def shutdown_memory_provider(self, messages: list = None) -> None:
            """Shut down the memory provider and context engine — call at actual session boundaries.

            This calls on_session_end() then shutdown_all() on the memory
            manager, and on_session_end() on the context engine.
            NOT called per-turn — only at CLI exit, /reset, gateway
            session expiry, etc.
            """
            if self._memory_manager:
                try:
                    self._memory_manager.on_session_end(messages or [])
                except Exception:
                    pass
                try:
                    self._memory_manager.shutdown_all()
                except Exception:
                    pass
            # Notify context engine of session end (flush DAG, close DBs, etc.)
            if hasattr(self, "context_compressor") and self.context_compressor:
                try:
                    self.context_compressor.on_session_end(
                        self.session_id or "",
                        messages or [],
                    )
                except Exception:
                    pass


    def commit_memory_session(self, messages: list = None) -> None:
            """Trigger end-of-session extraction without tearing providers down.
            Called when session_id rotates (e.g. /new, context compression);
            providers keep their state and continue running under the old
            session_id — they just flush pending extraction now."""
            if not self._memory_manager:
                return
            try:
                self._memory_manager.on_session_end(messages or [])
            except Exception:
                pass


    def _sync_external_memory_for_turn(
            self,
            *,
            original_user_message: Any,
            final_response: Any,
            interrupted: bool,
        ) -> None:
            """Mirror a completed turn into external memory providers.

            Called at the end of ``run_conversation`` with the cleaned user
            message (``original_user_message``) and the finalised assistant
            response.  The external memory backend gets both ``sync_all`` (to
            persist the exchange) and ``queue_prefetch_all`` (to start
            warming context for the next turn) in one shot.

            Uses ``original_user_message`` rather than ``user_message``
            because the latter may carry injected skill content that bloats
            or breaks provider queries.

            Interrupted turns are skipped entirely (#15218).  A partial
            assistant output, an aborted tool chain, or a mid-stream reset
            is not durable conversational truth — mirroring it into an
            external memory backend pollutes future recall with state the
            user never saw completed.  The prefetch is gated on the same
            flag: the user's next message is almost certainly a retry of
            the same intent, and a prefetch keyed on the interrupted turn
            would fire against stale context.

            Normal completed turns still sync as before.  The whole body is
            wrapped in ``try/except Exception`` because external memory
            providers are strictly best-effort — a misconfigured or offline
            backend must not block the user from seeing their response.
            """
            if interrupted:
                return
            if not (self._memory_manager and final_response and original_user_message):
                return
            try:
                self._memory_manager.sync_all(
                    original_user_message, final_response,
                    session_id=self.session_id or "",
                )
                self._memory_manager.queue_prefetch_all(
                    original_user_message,
                    session_id=self.session_id or "",
                )
            except Exception:
                pass


    def _hydrate_todo_store(self, history: List[Dict[str, Any]]) -> None:
            """
            Recover todo state from conversation history.

            The gateway creates a fresh AIAgent per message, so the in-memory
            TodoStore is empty. We scan the history for the most recent todo
            tool response and replay it to reconstruct the state.
            """
            # Walk history backwards to find the most recent todo tool response
            last_todo_response = None
            for msg in reversed(history):
                if msg.get("role") != "tool":
                    continue
                content = msg.get("content", "")
                # Quick check: todo responses contain "todos" key
                if '"todos"' not in content:
                    continue
                try:
                    data = json.loads(content)
                    if "todos" in data and isinstance(data["todos"], list):
                        last_todo_response = data["todos"]
                        break
                except (json.JSONDecodeError, TypeError):
                    continue

            if last_todo_response:
                # Replay the items into the store (replace mode)
                self._todo_store.write(last_todo_response, merge=False)
                if not self.quiet_mode:
                    self._vprint(f"{self.log_prefix}📋 Restored {len(last_todo_response)} todo item(s) from history")
            _set_interrupt(False)


