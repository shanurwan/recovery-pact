"""NVIDIA Nemotron inference client with recording and replay.

Uses the official NVIDIA NIM OpenAI-compatible Chat Completions API:
  Base URL: https://integrate.api.nvidia.com/v1
  Docs: https://docs.api.nvidia.com/nim/reference/llm-apis

INFERENCE_MODE=nemotron  live calls; every response is recorded under RECORD_DIR.
INFERENCE_MODE=replay    serves responses recorded from earlier live Nemotron runs,
                         keyed by (scenario, arm, memory state, agent, round). Every
                         replayed turn is labeled replay with the original model id,
                         so it is never presented as a live call. The deterministic
                         parts (grounding, authority, executor, verification) still
                         run live against PostgreSQL.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class ReplayMissing(RuntimeError):
    pass


class InferenceClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.mode = settings.inference_mode
        if self.mode == "nemotron" and not settings.nvidia_api_key:
            logger.warning("INFERENCE_MODE=nemotron but NVIDIA_API_KEY missing; using replay")
            self.mode = "replay"
        self.base_url = settings.nvidia_base_url.rstrip("/")
        self.model = settings.nemotron_model
        self.api_key = settings.nvidia_api_key
        self.timeout = settings.inference_timeout_seconds
        self.max_retries = settings.inference_max_retries
        self.temperature = settings.inference_temperature
        self.max_tokens = settings.inference_max_tokens
        self.thinking = settings.nemotron_thinking
        self.replay_dir = Path(settings.recordings_dir)
        self.record_dir = Path(settings.record_dir)

    @property
    def model_id(self) -> str:
        return self.model

    def _slug(self, model: str) -> str:
        return re.sub(r"[^a-zA-Z0-9.-]+", "_", model)

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        call_key: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (parsed JSON, metrics). Metrics always say where the answer came from."""
        if self.mode == "replay":
            return self._replay(call_key)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            # Reasoning tokens count against max_tokens; leave room for the answer.
            "max_tokens": self.max_tokens * 4 if self.thinking else self.max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": self.thinking},
        }
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
                        json=body,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                latency = (time.perf_counter() - started) * 1000
                msg = data["choices"][0]["message"]
                content = msg.get("content") or ""
                if not content.strip():
                    raise ValueError(f"empty content (finish_reason={data['choices'][0].get('finish_reason')})")
                parsed = parse_json(content)
                usage = data.get("usage") or {}
                metrics = {
                    "mode": "nemotron",
                    "model": self.model,
                    "latency_ms": round(latency, 1),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "attempt": attempt + 1,
                    "reasoning": (msg.get("reasoning_content") or "")[:2000],
                    "call_key": call_key,
                }
                self._record(call_key, messages, content, metrics)
                return parsed, metrics
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("inference attempt %s failed: %s", attempt + 1, exc)
                time.sleep(0.75 * (attempt + 1))
        raise RuntimeError(f"Inference failed after retries: {last_err}")

    def _record(self, call_key: str, messages: list[dict[str, str]], content: str, metrics: dict[str, Any]) -> None:
        path = self.record_dir / self._slug(self.model) / f"{call_key}.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"call_key": call_key, "messages": messages, "content": content, "metrics": metrics},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("could not record %s: %s", call_key, exc)

    def _replay(self, call_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
        path = self.replay_dir / self._slug(self.model) / f"{call_key}.json"
        if not path.exists():
            raise ReplayMissing(
                f"No recorded Nemotron response for {call_key} ({self.model}). "
                "Set NVIDIA_API_KEY and INFERENCE_MODE=nemotron to run live."
            )
        rec = json.loads(path.read_text(encoding="utf-8"))
        metrics = dict(rec.get("metrics") or {})
        metrics.update({"mode": "replay", "replayed_from": str(path.name), "latency_ms": 0})
        return parse_json(rec["content"]), metrics


def parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = "\n".join(ln for ln in text.split("\n") if not ln.strip().startswith("```"))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


_client: InferenceClient | None = None


def get_inference_client() -> InferenceClient:
    global _client
    if _client is None:
        _client = InferenceClient()
    return _client


def reset_inference_client() -> None:
    global _client
    _client = None
