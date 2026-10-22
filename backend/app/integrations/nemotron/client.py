"""Configurable Nemotron / fixture inference client.

Uses the official NVIDIA NIM OpenAI-compatible Chat Completions API:
  Base URL: https://integrate.api.nvidia.com/v1
  Docs: https://docs.api.nvidia.com/nim/reference/llm-apis

When INFERENCE_MODE=fixture or NVIDIA_API_KEY is absent, returns
deterministic structured fixtures explicitly labeled as non-sponsor runs.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class InferenceClient:
    def __init__(self) -> self:
        settings = get_settings()
        self.mode = settings.inference_mode
        if self.mode == "nemotron" and not settings.nvidia_api_key:
            logger.warning(
                "INFERENCE_MODE=nemotron but NVIDIA_API_KEY missing; falling back to fixture"
            )
            self.mode = "fixture"
        self.base_url = settings.nvidia_base_url.rstrip("/")
        self.model = settings.nemotron_model
        self.api_key = settings.nvidia_api_key
        self.timeout = settings.inference_timeout_seconds
        self.max_retries = settings.inference_max_retries
        self.temperature = settings.inference_temperature
        self.last_metrics: dict[str, Any] = {}

    @property
    def model_id(self) -> str:
        return self.model if self.mode == "nemotron" else "fixture-deterministic-v1"

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema_hint: str,
        fixture_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.mode == "fixture":
            if fixture_payload is None:
                raise ValueError("fixture mode requires fixture_payload")
            self.last_metrics = {
                "mode": "fixture",
                "model": self.model_id,
                "latency_ms": 0,
                "prompt_tokens": None,
                "completion_tokens": None,
                "sponsor_verified": False,
            }
            return fixture_payload

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"{user}\n\nRespond with ONLY valid JSON matching this shape:\n{schema_hint}"
                ),
            },
        ]
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": self.temperature,
                            "max_tokens": 2048,
                            "stream": False,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                latency = (time.perf_counter() - started) * 1000
                content = data["choices"][0]["message"]["content"]
                parsed = self._parse_json(content)
                usage = data.get("usage") or {}
                self.last_metrics = {
                    "mode": "nemotron",
                    "model": self.model,
                    "latency_ms": latency,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "sponsor_verified": True,
                    "attempt": attempt + 1,
                }
                return parsed
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("inference attempt %s failed: %s", attempt + 1, exc)
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"Inference failed after retries: {last_err}")

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines)
        return json.loads(text)


_client: InferenceClient | None = None


def get_inference_client() -> InferenceClient:
    global _client
    if _client is None:
        _client = InferenceClient()
    return _client
