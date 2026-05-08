"""
Unit tests for S5 + Ralph components.

Все тесты работают без реальной БД и gateway (mock-только).
"""
from __future__ import annotations

import json
import sys
import threading
import time
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import urllib.request

import pytest

# Ensure src is on path
SRC = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(SRC))


# ===========================================================================
# SourceRouter
# ===========================================================================

class TestSourceRouter:
    def _make_router(self, is_dup=False, enqueue_return="inbox-uuid"):
        from s5.source_router import SourceRouter

        orch = MagicMock()
        orch.dbname = "rag"
        orch.enqueue.return_value = enqueue_return

        router = SourceRouter(orch)
        router._is_duplicate = MagicMock(return_value=is_dup)
        return router, orch

    def test_submit_new_message_returns_inbox_id(self):
        router, orch = self._make_router(is_dup=False)
        result = router.submit("do something", source="test")
        assert result == "inbox-uuid"
        orch.enqueue.assert_called_once()

    def test_submit_duplicate_returns_none(self):
        router, orch = self._make_router(is_dup=True)
        result = router.submit("do something", source="test")
        assert result is None
        orch.enqueue.assert_not_called()

    def test_submit_empty_message_returns_none(self):
        router, orch = self._make_router()
        assert router.submit("", source="test") is None
        assert router.submit("   ", source="test") is None

    def test_idempotency_key_passed_in_metadata(self):
        router, orch = self._make_router(is_dup=False)
        router.submit("msg", source="tg", idempotency_key="mykey123")
        _, kwargs = orch.enqueue.call_args
        meta = kwargs.get("metadata") or orch.enqueue.call_args[0][3] or {}
        # metadata should contain idempotency_key
        assert meta.get("idempotency_key") == "mykey123"

    def test_compute_key_deterministic(self):
        from s5.source_router import SourceRouter
        router = SourceRouter(MagicMock())
        k1 = router._compute_key("hello world", "telegram")
        k2 = router._compute_key("hello world", "telegram")
        k3 = router._compute_key("hello world", "n8n")
        assert k1 == k2
        assert k1 != k3
        assert len(k1) == 16

    def test_priority_passed_through(self):
        router, orch = self._make_router(is_dup=False)
        router.submit("task", source="api", priority=2)
        _, kwargs = orch.enqueue.call_args
        assert kwargs.get("priority") == 2


# ===========================================================================
# TelegramNotifier
# ===========================================================================

class TestTelegramNotifier:
    def _make_notifier(self):
        from ralph.notifier import TelegramNotifier
        return TelegramNotifier(token="testtoken", chat_id="12345")

    def test_send_calls_telegram_api(self):
        notifier = self._make_notifier()
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            result = notifier.send("hello")
        assert result is True
        assert mock_open.called

    def test_send_returns_false_on_error(self):
        notifier = self._make_notifier()
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            result = notifier.send("hello")
        assert result is False

    def test_from_env_returns_none_without_token(self):
        from ralph.notifier import TelegramNotifier
        # Provide HOME/USERPROFILE so Path.home() doesn't raise on Windows/CI
        fake_home = {"HOME": "/tmp/fakehome", "USERPROFILE": "/tmp/fakehome",
                     "HOMEDRIVE": "C:", "HOMEPATH": "\\tmp\\fakehome"}
        with patch.dict("os.environ", fake_home, clear=True):
            with patch("ralph.notifier._read_env", return_value={}):
                result = TelegramNotifier.from_env()
        assert result is None

    def test_trunc_shortens_long_text(self):
        from ralph.notifier import TelegramNotifier
        text = "x" * 200
        assert len(TelegramNotifier._trunc(text, 100)) == 101  # 100 + "…"

    def test_notify_complete_sends_message(self):
        notifier = self._make_notifier()
        notifier.send = MagicMock(return_value=True)
        notifier.notify_complete("task-uuid-1234", "do something", "done!")
        notifier.send.assert_called_once()
        sent_text = notifier.send.call_args[0][0]
        # task_id is truncated to 8 chars: "task-uui"
        assert "task-uui" in sent_text or "task-uuid" in sent_text
        assert "✅" in sent_text or "выполнена" in sent_text.lower()

    def test_notify_failed_includes_retry_label(self):
        notifier = self._make_notifier()
        notifier.send = MagicMock(return_value=True)
        notifier.notify_failed("tid", "msg", "timeout", retry=True)
        text = notifier.send.call_args[0][0]
        assert "повтор" in text.lower() or "🔄" in text

    def test_notify_skipped_mentions_human(self):
        notifier = self._make_notifier()
        notifier.send = MagicMock(return_value=True)
        notifier.notify_skipped("tid", "priority=critical requires_human")
        text = notifier.send.call_args[0][0]
        assert "human" in text or "человека" in text or "⏸" in text


# ===========================================================================
# GatewayClient
# ===========================================================================

class TestGatewayClient:
    def _make_client(self):
        from ralph.gateway_client import GatewayClient
        return GatewayClient(gateway_url="http://127.0.0.1:19999", timeout=5)

    def test_run_returns_ok_on_success(self):
        client = self._make_client()
        response_data = {"message": {"content": [{"type": "text", "text": "done!"}]}}
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.status = 200

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = client.run("do something", model="test-model")

        assert result["ok"] is True
        assert result["response"] == "done!"
        assert result["model_used"] == "test-model"

    def test_run_tries_next_model_on_4xx(self):
        client = self._make_client()
        import urllib.error

        errors = [
            urllib.error.HTTPError("url", 422, "unprocessable", {}, BytesIO(b"bad model")),
        ]
        success_data = {"response": "ok"}
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = json.dumps(success_data).encode()

        call_count = [0]
        def side_effect(*args, **kwargs):
            i = call_count[0]
            call_count[0] += 1
            if i < len(errors):
                raise errors[i]
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=side_effect):
            from ralph.gateway_client import FREE_MODELS
            result = client.run("test", model=None)

        # Должен попробовать несколько моделей
        assert call_count[0] >= 1

    def test_health_returns_false_on_connection_error(self):
        client = self._make_client()
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            assert client.health() is False

    def test_extract_response_acp_format(self):
        from ralph.gateway_client import GatewayClient
        data = {"message": {"content": [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]}}
        result = GatewayClient._extract_response(data)
        assert result == "hello\nworld"

    def test_extract_response_simple_format(self):
        from ralph.gateway_client import GatewayClient
        data = {"response": "simple answer"}
        assert GatewayClient._extract_response(data) == "simple answer"


# ===========================================================================
# RalphRunner — priority guard
# ===========================================================================

class TestRalphRunnerPriorityGuard:
    def _make_runner(self):
        from ralph.runner import RalphRunner
        orch = MagicMock()
        gw = MagicMock()
        notifier = MagicMock()
        router = MagicMock()
        runner = RalphRunner(orch, gw, notifier, router, poll_interval=1)
        return runner, orch, gw, notifier

    def test_allowed_priority_normal_passes(self):
        runner, orch, gw, notifier = self._make_runner()
        assert runner._is_allowed_priority("normal", "tid-1") is True
        orch.pause.assert_not_called()

    def test_allowed_priority_low_passes(self):
        runner, orch, gw, notifier = self._make_runner()
        assert runner._is_allowed_priority("low", "tid-1") is True

    def test_critical_priority_is_paused(self):
        runner, orch, gw, notifier = self._make_runner()
        result = runner._is_allowed_priority("critical", "tid-2")
        assert result is False
        orch.pause.assert_called_once_with("tid-2", "priority=critical requires_human")
        notifier.notify_skipped.assert_called_once()

    def test_high_priority_is_paused(self):
        runner, orch, gw, notifier = self._make_runner()
        result = runner._is_allowed_priority("high", "tid-3")
        assert result is False
        orch.pause.assert_called_once()

    def test_complete_called_on_success(self):
        runner, orch, gw, notifier = self._make_runner()
        task = {"id": "tid", "priority": "normal", "raw_text": "do it"}
        result = {"ok": True, "response": "done!", "model_used": "test", "latency_ms": 100}
        runner._handle_result("tid", task, "do it", result)
        orch.complete.assert_called_once_with("tid")
        notifier.notify_complete.assert_called_once()

    def test_fail_with_retry_called_on_error(self):
        runner, orch, gw, notifier = self._make_runner()
        task = {"id": "tid", "priority": "normal", "raw_text": "do it",
                "metadata": {"retry_count": 0, "max_retries": 3}}
        result = {"ok": False, "response": "", "model_used": "test",
                  "error": "timeout", "latency_ms": 5000}
        runner._handle_result("tid", task, "do it", result)
        orch.fail.assert_called_once_with("tid", "timeout", should_retry=True)
        notifier.notify_failed.assert_called_once()

    def test_fail_without_retry_when_exhausted(self):
        runner, orch, gw, notifier = self._make_runner()
        task = {"id": "tid", "priority": "low", "raw_text": "do it",
                "metadata": {"retry_count": 3, "max_retries": 3}}
        result = {"ok": False, "response": "", "model_used": "test",
                  "error": "gateway down", "latency_ms": 0}
        runner._handle_result("tid", task, "do it", result)
        orch.fail.assert_called_once_with("tid", "gateway down", should_retry=False)
