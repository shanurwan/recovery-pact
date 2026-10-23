"""Nemotron inference client with recording and replay.

Two providers, both OpenAI-compatible:
  AI_PROVIDER=meterless (primary)  Meterless Runtime / Nightshift, which serves the
      Nemotron models assigned to its lanes. See app/integrations/meterless/runtime.py.
  AI_PROVIDER=nvidia               the NVIDIA NIM API directly
      (https://integrate.api.nvidia.com/v1, docs.api.nvidia.com/nim/reference/llm-apis).

Agents ask for a logical Nemotron model (NEMOTRON_MODEL, MODEL_<ROLE>); with
Meterless it is mapped to a route (METERLESS_ROUTES / METERLESS_MODEL) and the
model Nightshift actually served is recorded with every call.

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
from app.integrations.meterless import runtime as meterless

logger = logging.getLogger(__name__)


RATE_LIMIT_RETRIES = 8


class ReplayMissing(RuntimeError):
    pass


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        v = float(resp.headers.get("retry-after", ""))
        return max(1.0, min(v, 60.0))
    except ValueError:
        return None


class InferenceClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.mode = "replay" if settings.sample_mode else settings.inference_mode
        self.provider = settings.ai_provider
        self.settings = settings
        if self.mode == "nemotron":
            if self.provider == "meterless" and settings.meterless_runtime_token.strip() in meterless.PLACEHOLDER_TOKENS:
                logger.warning("AI_PROVIDER=meterless but METERLESS_RUNTIME_TOKEN is missing; using replay")
                self.mode = "replay"
            elif self.provider == "nvidia" and not settings.nvidia_api_key:
                logger.warning("AI_PROVIDER=nvidia but NVIDIA_API_KEY missing; using replay")
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
        model: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (parsed JSON, metrics). Metrics always say where the answer came from."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        model = model or self.model
        body: dict[str, Any] = {
            "temperature": self.temperature,
            # Reasoning tokens count against max_tokens; leave room for the answer.
            "max_tokens": self.max_tokens * 4 if self.thinking else self.max_tokens,
            "chat_template_kwargs": {"enable_thinking": self.thinking},
        }
        content, metrics = self._chat(model, messages, call_key, body, require_json=True)
        return parse_json(content), metrics

    def complete_text(
        self,
        *,
        user: str,
        call_key: str,
        model: str,
        max_tokens: int = 120,
    ) -> tuple[str, dict[str, Any]]:
        """Plain-text call (used by the safety guard), recorded and replayable like the rest."""
        content, metrics = self._chat(
            model, [{"role": "user", "content": user}], call_key, {"temperature": 0, "max_tokens": max_tokens}, require_json=False
        )
        return content, metrics

    def _chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        call_key: str,
        extra: dict[str, Any],
        require_json: bool,
    ) -> tuple[str, dict[str, Any]]:
        if self.mode == "replay":
            return self._replay(call_key, model)
        if self.provider == "meterless":
            url = f"{meterless.normalize_base_url(self.settings.meterless_base_url)}/chat/completions"
            hdrs = meterless.headers(self.settings.meterless_runtime_token, chat=True)
            wire_model = self.settings.meterless_route(model)
            timeout = max(self.timeout, meterless.TIMEOUT_S)
            if not self.thinking:
                extra = {k: v for k, v in extra.items() if k != "chat_template_kwargs"}
        else:
            url = f"{self.base_url}/chat/completions"
            hdrs = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "Accept": "application/json"}
            wire_model = model
            timeout = self.timeout
        body: dict[str, Any] = {"model": wire_model, "messages": messages, "stream": False, **extra}
        last_err: Exception | None = None
        attempt = 0
        throttled = 0
        waited = 0.0
        while attempt <= self.max_retries:
            started = time.perf_counter()
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(url, headers=hdrs, json=body)
                    if self.provider == "meterless" and resp.status_code in (401, 403):
                        raise RuntimeError(f"Meterless Runtime refused the token (HTTP {resp.status_code}); "
                                           "copy the Runtime API key from the Nightshift Console")
                    # Rate limiting is the API's capacity, not the model's answer: wait it out
                    # (Retry-After or exponential backoff) without spending a real attempt.
                    if resp.status_code in (429, 503) and throttled < RATE_LIMIT_RETRIES:
                        delay = _retry_after(resp) or min(60.0, 2.0 * (2 ** throttled))
                        throttled += 1
                        waited += delay
                        logger.info("%s throttled (%s); waiting %.0fs", model, resp.status_code, delay)
                        time.sleep(delay)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                latency = (time.perf_counter() - started) * 1000
                msg = data["choices"][0]["message"]
                content = msg.get("content") or ""
                # Some routes return their reasoning inline ("...</think>answer"); keep the answer.
                if "</think>" in content:
                    content = content.rsplit("</think>", 1)[1].strip()
                if not content.strip():
                    raise ValueError(f"empty content (finish_reason={data['choices'][0].get('finish_reason')})")
                if require_json:
                    parse_json(content)  # malformed JSON is retried like a transport error
                usage = data.get("usage") or {}
                metrics = {
                    "mode": "nemotron",
                    "model": model,
                    "provider": self.provider,
                    "route": wire_model,
                    "served_by": data.get("model") or wire_model,
                    # Nightshift's signed receipt for this call carries the same id (receipt.request_id).
                    "response_id": data.get("id"),
                    "latency_ms": round(latency, 1),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "attempt": attempt + 1,
                    "rate_limit_wait_s": round(waited, 1),
                    "reasoning": (msg.get("reasoning_content") or "")[:2000],
                    "call_key": call_key,
                }
                self._record(call_key, model, messages, content, metrics)
                return content, metrics
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("inference attempt %s failed: %s", attempt + 1, exc)
                attempt += 1
                time.sleep(0.75 * attempt)
        raise RuntimeError(f"Inference failed after retries: {last_err}")

    def _record(self, call_key: str, model: str, messages: list[dict[str, str]], content: str, metrics: dict[str, Any]) -> None:
        path = self.record_dir / self._slug(model) / f"{call_key}.json"
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

    def _replay(self, call_key: str, model: str) -> tuple[str, dict[str, Any]]:
        path = self.replay_dir / self._slug(model) / f"{call_key}.json"
        if not path.exists():
            # The run may name a different model than the recording (another provider or
            # role mapping); a call key recorded under exactly one model is unambiguous.
            hits = list(self.replay_dir.glob(f"*/{call_key}.json"))
            if len(hits) == 1:
                path = hits[0]
        if not path.exists():
            raise ReplayMissing(
                f"No recorded Nemotron response for {call_key} ({model}). "
                "Set NVIDIA_API_KEY and INFERENCE_MODE=nemotron to run live."
            )
        rec = json.loads(path.read_text(encoding="utf-8"))
        metrics = dict(rec.get("metrics") or {})
        metrics.update({"mode": "replay", "replayed_from": str(path.name), "latency_ms": 0})
        return rec["content"], metrics


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
