"""
GatewayClient — HTTP-клиент к Hermes Gateway (ACP).

Предпочитает бесплатные NVIDIA NIM модели. Никогда не выбирает
платные OpenRouter модели автономно — только если передан явный model=.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Iterator
from urllib import request, error as urllib_error

log = logging.getLogger(__name__)

# Бесплатные NVIDIA NIM модели, упорядоченные по предпочтению.
# Обновлять при изменении каталога NIM (см. docs/phase_10_task_plan.json).
FREE_MODELS: list[str] = [
    "qwen/qwen3-next-80b-a3b-instruct",         # MoE, бесплатный
    "nvidia/nemotron-3-super-120b-a12b",         # гибрид Mamba-MoE
    "meta/llama-3.1-70b-instruct",               # dense, бесплатный
    "meta/llama-3.1-8b-instruct",                # быстрый fallback
]

ACP_RUNS_PATH = "/acp/v1/runs"
HEALTH_PATH = "/health"


class GatewayClient:
    """
    Клиент к Hermes Gateway.

    run() пробует FREE_MODELS по порядку пока один не ответит успешно.
    Платные модели используются только если передать model= явно.
    """

    def __init__(
        self,
        gateway_url: str = "http://127.0.0.1:8000",
        timeout: int = 300,
        max_retries: int = 1,
    ) -> None:
        self._url = gateway_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        message: str,
        model: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        """
        Отправить задачу в gateway и дождаться ответа.

        Args:
            message:  текст задачи
            model:    явная модель; если None — выбирается из FREE_MODELS
            task_id:  опциональный идентификатор для логов

        Returns:
            {
                "ok":         bool,
                "response":   str,   # текст ответа агента
                "model_used": str,
                "error":      str | None,
                "latency_ms": int,
            }
        """
        models_to_try = [model] if model else list(FREE_MODELS)
        last_error: str = "no models available"

        for m in models_to_try:
            t0 = time.monotonic()
            result = self._try_run(message=message, model=m, task_id=task_id)
            latency = int((time.monotonic() - t0) * 1000)
            result["latency_ms"] = latency

            if result["ok"]:
                log.info(
                    "GatewayClient: task_id=%s model=%s latency=%dms",
                    task_id or "?", m, latency,
                )
                return result

            last_error = result.get("error", "unknown")
            log.warning(
                "GatewayClient: model=%s failed (%s), trying next", m, last_error
            )

        return {
            "ok": False,
            "response": "",
            "model_used": models_to_try[-1] if models_to_try else "",
            "error": last_error,
            "latency_ms": 0,
        }

    def health(self) -> bool:
        """Проверить что gateway жив. True = ок."""
        try:
            req = request.Request(self._url + HEALTH_PATH)
            with request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _try_run(self, message: str, model: str, task_id: str | None) -> dict:
        payload = {"message": message, "model": model}
        if task_id:
            payload["metadata"] = {"ralph_task_id": task_id}

        body = json.dumps(payload).encode()
        req = request.Request(
            self._url + ACP_RUNS_PATH,
            data=body,
            headers={"Content-Type": "application/json"},
        )

        for attempt in range(self._max_retries + 1):
            try:
                with request.urlopen(req, timeout=self._timeout) as resp:
                    raw = resp.read()
                    data = json.loads(raw) if raw else {}
                    # Gateway возвращает разные форматы — нормализуем
                    response_text = self._extract_response(data)
                    return {
                        "ok": True,
                        "response": response_text,
                        "model_used": model,
                        "error": None,
                    }
            except urllib_error.HTTPError as exc:
                error_body = ""
                try:
                    error_body = exc.read().decode("utf-8", errors="replace")[:300]
                except Exception:
                    pass
                # 4xx — не ретраить
                if exc.code >= 400 and exc.code < 500:
                    return {
                        "ok": False,
                        "response": "",
                        "model_used": model,
                        "error": f"HTTP {exc.code}: {error_body}",
                    }
                if attempt < self._max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return {
                    "ok": False,
                    "response": "",
                    "model_used": model,
                    "error": f"HTTP {exc.code}: {error_body}",
                }
            except urllib_error.URLError as exc:
                if attempt < self._max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return {
                    "ok": False,
                    "response": "",
                    "model_used": model,
                    "error": f"connection error: {exc.reason}",
                }
            except Exception as exc:
                return {
                    "ok": False,
                    "response": "",
                    "model_used": model,
                    "error": f"unexpected: {exc}",
                }

        return {"ok": False, "response": "", "model_used": model, "error": "max retries exceeded"}

    @staticmethod
    def _extract_response(data: dict) -> str:
        """Извлечь текст ответа из разных форматов gateway response."""
        # ACP формат: {"message": {"content": [{"text": "..."}]}}
        msg = data.get("message") or {}
        if isinstance(msg, dict):
            content = msg.get("content") or []
            if isinstance(content, list):
                parts = [
                    c.get("text", "") for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                if parts:
                    return "\n".join(parts)
            if isinstance(content, str):
                return content

        # Простой формат: {"response": "..."}
        if "response" in data:
            return str(data["response"])

        # Fallback: весь JSON
        return json.dumps(data, ensure_ascii=False)[:2000]
