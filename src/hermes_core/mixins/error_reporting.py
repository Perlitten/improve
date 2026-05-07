import logging
import json
import asyncio
import time
import uuid
import httpx
import threading
import sys
import os
import re
import copy
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple

from utils import env_var_enabled
from agent.usage_pricing import normalize_usage

logger = logging.getLogger(__name__)

class ErrorReportingMixin:
    def _summarize_api_error(error: Exception) -> str:
            """Extract a human-readable one-liner from an API error.

            Handles Cloudflare HTML error pages (502, 503, etc.) by pulling the
            <title> tag instead of dumping raw HTML.  Falls back to a truncated
            str(error) for everything else.
            """
            raw = str(error)

            # Cloudflare / proxy HTML pages: grab the <title> for a clean summary
            if "<!DOCTYPE" in raw or "<html" in raw:
                m = re.search(r"<title[^>]*>([^<]+)</title>", raw, re.IGNORECASE)
                title = m.group(1).strip() if m else "HTML error page (title not found)"
                # Also grab Cloudflare Ray ID if present
                ray = re.search(r"Cloudflare Ray ID:\s*<strong[^>]*>([^<]+)</strong>", raw)
                ray_id = ray.group(1).strip() if ray else None
                status_code = getattr(error, "status_code", None)
                parts = []
                if status_code:
                    parts.append(f"HTTP {status_code}")
                parts.append(title)
                if ray_id:
                    parts.append(f"Ray {ray_id}")
                return " — ".join(parts)

            # JSON body errors from OpenAI/Anthropic SDKs
            body = getattr(error, "body", None)
            if isinstance(body, dict):
                msg = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("message")
                if msg:
                    status_code = getattr(error, "status_code", None)
                    prefix = f"HTTP {status_code}: " if status_code else ""
                    return f"{prefix}{msg[:300]}"

            # Fallback: truncate the raw string but give more room than 200 chars
            status_code = getattr(error, "status_code", None)
            prefix = f"HTTP {status_code}: " if status_code else ""
            return f"{prefix}{raw[:500]}"


    def _mask_api_key_for_logs(self, key: Optional[str]) -> Optional[str]:
            if not key:
                return None
            if len(key) <= 12:
                return "***"
            return f"{key[:8]}...{key[-4:]}"


    def _clean_error_message(self, error_msg: str) -> str:
            """
            Clean up error messages for user display, removing HTML content and truncating.

            Args:
                error_msg: Raw error message from API or exception

            Returns:
                Clean, user-friendly error message
            """
            if not error_msg:
                return "Unknown error"

            # Remove HTML content (common with CloudFlare and gateway error pages)
            if error_msg.strip().startswith('<!DOCTYPE html') or '<html' in error_msg:
                return "Service temporarily unavailable (HTML error page returned)"

            # Remove newlines and excessive whitespace
            cleaned = ' '.join(error_msg.split())

            # Truncate if too long
            if len(cleaned) > 150:
                cleaned = cleaned[:150] + "..."

            return cleaned


    def _extract_api_error_context(error: Exception) -> Dict[str, Any]:
            """Extract structured rate-limit details from provider errors."""
            context: Dict[str, Any] = {}

            body = getattr(error, "body", None)
            payload = None
            if isinstance(body, dict):
                payload = body.get("error") if isinstance(body.get("error"), dict) else body
            if isinstance(payload, dict):
                reason = payload.get("code") or payload.get("error")
                if isinstance(reason, str) and reason.strip():
                    context["reason"] = reason.strip()
                message = payload.get("message") or payload.get("error_description")
                if isinstance(message, str) and message.strip():
                    context["message"] = message.strip()
                for key in ("resets_at", "reset_at"):
                    value = payload.get(key)
                    if value not in (None, ""):
                        context["reset_at"] = value
                        break
                retry_after = payload.get("retry_after")
                if retry_after not in (None, "") and "reset_at" not in context:
                    try:
                        context["reset_at"] = time.time() + float(retry_after)
                    except (TypeError, ValueError):
                        pass

            response = getattr(error, "response", None)
            headers = getattr(response, "headers", None)
            if headers:
                retry_after = headers.get("retry-after") or headers.get("Retry-After")
                if retry_after and "reset_at" not in context:
                    try:
                        context["reset_at"] = time.time() + float(retry_after)
                    except (TypeError, ValueError):
                        pass
                ratelimit_reset = headers.get("x-ratelimit-reset")
                if ratelimit_reset and "reset_at" not in context:
                    context["reset_at"] = ratelimit_reset

            if "message" not in context:
                raw_message = str(error).strip()
                if raw_message:
                    context["message"] = raw_message[:500]

            if "reset_at" not in context:
                message = context.get("message") or ""
                if isinstance(message, str):
                    delay_match = re.search(r"quotaResetDelay[:\s\"]+(\\d+(?:\\.\\d+)?)(ms|s)", message, re.IGNORECASE)
                    if delay_match:
                        value = float(delay_match.group(1))
                        seconds = value / 1000.0 if delay_match.group(2).lower() == "ms" else value
                        context["reset_at"] = time.time() + seconds
                    else:
                        sec_match = re.search(
                            r"retry\s+(?:after\s+)?(\d+(?:\.\d+)?)\s*(?:sec|secs|seconds|s\b)",
                            message,
                            re.IGNORECASE,
                        )
                        if sec_match:
                            context["reset_at"] = time.time() + float(sec_match.group(1))

            return context


    def _usage_summary_for_api_request_hook(self, response: Any) -> Optional[Dict[str, Any]]:
            """Token buckets for ``post_api_request`` plugins (no raw ``response`` object)."""
            if response is None:
                return None
            raw_usage = getattr(response, "usage", None)
            if not raw_usage:
                return None
            from dataclasses import asdict

            cu = normalize_usage(raw_usage, provider=self.provider, api_mode=self.api_mode)
            summary = asdict(cu)
            summary.pop("raw_usage", None)
            summary["prompt_tokens"] = cu.prompt_tokens
            summary["total_tokens"] = cu.total_tokens
            return summary


    def _dump_api_request_debug(
            self,
            api_kwargs: Dict[str, Any],
            *,
            reason: str,
            error: Optional[Exception] = None,
        ) -> Optional[Path]:
            """
            Dump a debug-friendly HTTP request record for the active inference API.

            Captures the request body from api_kwargs (excluding transport-only keys
            like timeout). Intended for debugging provider-side 4xx failures where
            retries are not useful.
            """
            try:
                body = copy.deepcopy(api_kwargs)
                body.pop("timeout", None)
                body = {k: v for k, v in body.items() if v is not None}

                api_key = None
                try:
                    api_key = getattr(self.client, "api_key", None)
                except Exception as e:
                    logger.debug("Could not extract API key for debug dump: %s", e)

                dump_payload: Dict[str, Any] = {
                    "timestamp": datetime.now().isoformat(),
                    "session_id": self.session_id,
                    "reason": reason,
                    "request": {
                        "method": "POST",
                        "url": f"{self.base_url.rstrip('/')}{'/responses' if self.api_mode == 'codex_responses' else '/chat/completions'}",
                        "headers": {
                            "Authorization": f"Bearer {self._mask_api_key_for_logs(api_key)}",
                            "Content-Type": "application/json",
                        },
                        "body": body,
                    },
                }

                if error is not None:
                    error_info: Dict[str, Any] = {
                        "type": type(error).__name__,
                        "message": str(error),
                    }
                    for attr_name in ("status_code", "request_id", "code", "param", "type"):
                        attr_value = getattr(error, attr_name, None)
                        if attr_value is not None:
                            error_info[attr_name] = attr_value

                    body_attr = getattr(error, "body", None)
                    if body_attr is not None:
                        error_info["body"] = body_attr

                    response_obj = getattr(error, "response", None)
                    if response_obj is not None:
                        try:
                            error_info["response_status"] = getattr(response_obj, "status_code", None)
                            error_info["response_text"] = response_obj.text
                        except Exception as e:
                            logger.debug("Could not extract error response details: %s", e)

                    dump_payload["error"] = error_info

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                dump_file = self.logs_dir / f"request_dump_{self.session_id}_{timestamp}.json"
                dump_file.write_text(
                    json.dumps(dump_payload, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )

                self._vprint(f"{self.log_prefix}🧾 Request debug dump written to: {dump_file}")

                if env_var_enabled("HERMES_DUMP_REQUEST_STDOUT"):
                    print(json.dumps(dump_payload, ensure_ascii=False, indent=2, default=str))

                return dump_file
            except Exception as dump_error:
                if self.verbose_logging:
                    logging.warning(f"Failed to dump API request debug payload: {dump_error}")
                return None


    def _safe_print(self, *args, **kwargs):
            """Print that silently handles broken pipes / closed stdout.

            In headless environments (systemd, Docker, nohup) stdout may become
            unavailable mid-session.  A raw ``print()`` raises ``OSError`` which
            can crash cron jobs and lose completed work.

            Internally routes through ``self._print_fn`` (default: builtin
            ``print``) so callers such as the CLI can inject a renderer that
            handles ANSI escape sequences properly (e.g. prompt_toolkit's
            ``print_formatted_text(ANSI(...))``) without touching this method.
            """
            try:
                fn = self._print_fn or print
                fn(*args, **kwargs)
            except (OSError, ValueError):
                pass


    def _vprint(self, *args, force: bool = False, **kwargs):
            """Verbose print — suppressed when actively streaming tokens.

            Pass ``force=True`` for error/warning messages that should always be
            shown even during streaming playback (TTS or display).

            During tool execution (``_executing_tools`` is True), printing is
            allowed even with stream consumers registered because no tokens
            are being streamed at that point.

            After the main response has been delivered and the remaining tool
            calls are post-response housekeeping (``_mute_post_response``),
            all non-forced output is suppressed.

            ``suppress_status_output`` is a stricter CLI automation mode used by
            parseable single-query flows such as ``hermes chat -q``. In that mode,
            all status/diagnostic prints routed through ``_vprint`` are suppressed
            so stdout stays machine-readable.
            """
            if getattr(self, "suppress_status_output", False):
                return
            if not force and getattr(self, "_mute_post_response", False):
                return
            if not force and self._has_stream_consumers() and not self._executing_tools:
                return
            self._safe_print(*args, **kwargs)


    def _emit_status(self, message: str) -> None:
            """Emit a lifecycle status message to both CLI and gateway channels.

            CLI users see the message via ``_vprint(force=True)`` so it is always
            visible regardless of verbose/quiet mode.  Gateway consumers receive
            it through ``status_callback("lifecycle", ...)``.

            This helper never raises — exceptions are swallowed so it cannot
            interrupt the retry/fallback logic.
            """
            try:
                self._vprint(f"{self.log_prefix}{message}", force=True)
            except Exception:
                pass
            if self.status_callback:
                try:
                    self.status_callback("lifecycle", message)
                except Exception:
                    logger.debug("status_callback error in _emit_status", exc_info=True)


    def _emit_warning(self, message: str) -> None:
            """Emit a user-visible warning through the same status plumbing.

            Unlike debug logs, these warnings are meant for degraded side paths
            such as auxiliary compression or memory flushes where the main turn can
            continue but the user needs to know something important failed.
            """
            try:
                self._vprint(f"{self.log_prefix}{message}", force=True)
            except Exception:
                pass
            if self.status_callback:
                try:
                    self.status_callback("warn", message)
                except Exception:
                    logger.debug("status_callback error in _emit_warning", exc_info=True)


    def _emit_auxiliary_failure(self, task: str, exc: BaseException) -> None:
            """Surface a compact warning for failed auxiliary work."""
            try:
                detail = self._summarize_api_error(exc)
            except Exception:
                detail = str(exc)
            detail = (detail or exc.__class__.__name__).strip()
            if len(detail) > 220:
                detail = detail[:217].rstrip() + "..."
            self._emit_warning(f"⚠ Auxiliary {task} failed: {detail}")


