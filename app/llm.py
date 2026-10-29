"""Nebius Token Factory client (OpenAI-compatible) with automatic Nemotron model resolution.

ScamShield uses three NVIDIA Nemotron tiers, each for what it is good at:
  fast   -> Nemotron 3 Super (thinking off) : entity extraction, plain-language family explanations
  reason -> Nemotron 3 Ultra (thinking on)  : evidence-weighing verdict
  vision -> Nemotron VL / Omni              : reading screenshots of messages
Super is preferred over Nano for "fast" because it measured ~0.8s vs ~6s median on Token Factory
(eval/latency.md); Nano remains the fallback.
"""
import json
import os
import re
import time

import httpx

BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1").rstrip("/")

# Ordered preferences: first model id containing all tokens (case-insensitive) wins.
PREFERENCES = {
    "fast": [["nemotron-3", "super"], ["nemotron", "super"], ["nemotron-3", "nano"], ["nemotron", "nano"]],
    "reason": [["nemotron-3", "ultra"], ["nemotron", "ultra"], ["nemotron-3", "super"], ["nemotron", "super"]],
    "vision": [["nemotron", "omni"], ["nemotron", "vl"], ["nemotron", "vision"]],
}
FAST_EXCLUDE = ("omni", "vl", "vision", "embed", "rerank", "reward", "safety", "guard")

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class LLMError(RuntimeError):
    pass


class TokenFactory:
    def __init__(self):
        self.api_key = os.getenv("NEBIUS_API_KEY", "").strip()
        self.models = {
            "fast": os.getenv("FAST_MODEL", "").strip(),
            "reason": os.getenv("REASON_MODEL", "").strip(),
            "vision": os.getenv("VISION_MODEL", "").strip(),
        }
        self.available: list[str] = []
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(180, connect=15),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def resolve_models(self) -> dict:
        """Fill any model not pinned via env by matching the live /models catalogue."""
        if not self.configured:
            return self.models
        resp = await self.client.get("/models")
        resp.raise_for_status()
        self.available = sorted(m["id"] for m in resp.json().get("data", []))
        for role, prefs in PREFERENCES.items():
            if self.models[role]:
                continue
            for tokens in prefs:
                match = [
                    m for m in self.available
                    if all(t in m.lower() for t in tokens)
                    and not (role == "fast" and any(x in m.lower() for x in FAST_EXCLUDE))
                    and not (role == "reason" and any(x in m.lower() for x in FAST_EXCLUDE))
                ]
                if match:
                    self.models[role] = match[0]
                    break
        if not self.models["reason"]:
            self.models["reason"] = self.models["fast"]
        return self.models

    async def chat(self, role: str, messages: list, *, max_tokens=1500, temperature=0.2, json_mode=False, think=None) -> dict:
        model = self.models.get(role)
        if not model:
            raise LLMError(f"No Nemotron model resolved for role '{role}'")
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        # Nemotron 3 reasoning toggle: think only where it pays off (the verdict).
        body["chat_template_kwargs"] = {"enable_thinking": role == "reason" if think is None else think}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        resp = await self.client.post("/chat/completions", json=body)
        if resp.status_code == 400 and json_mode:
            # Some models reject response_format; the prompt already demands JSON.
            body.pop("response_format")
            resp = await self.client.post("/chat/completions", json=body)
        if resp.status_code >= 400:
            raise LLMError(f"Token Factory {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        msg = data["choices"][0]["message"]
        text = THINK_RE.sub("", msg.get("content") or "").strip()
        return {
            "text": text,
            "model": model,
            "ms": int((time.perf_counter() - t0) * 1000),
            "usage": data.get("usage", {}),
        }

    async def chat_json(self, role: str, messages: list, **kw) -> tuple[dict, dict]:
        out = await self.chat(role, messages, json_mode=True, **kw)
        return parse_json(out["text"]), out


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise LLMError(f"Model did not return JSON: {text[:200]}")
