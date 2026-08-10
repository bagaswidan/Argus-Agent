"""Provider — Argus Brain.

OpenAI-compatible chat provider (OmniRoute / OpenRouter / any OpenAI-compatible
endpoint) using only the standard library. Key detail: OmniRoute defaults to
SSE streaming, so we always send ``stream: false`` explicitly.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class ChatResponse:
    content: str
    model: str
    provider_id: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.content)


class OmniRouteProvider:
    """OpenAI-compatible chat provider.

    Args:
        base_url: endpoint base, e.g. http://127.0.0.1:20128/v1
        api_key: optional bearer token (OmniRoute accepts any non-empty key)
        model: default model id (combo name or model id)
        timeout: request timeout in seconds
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:20128/v1",
        api_key: Optional[str] = None,
        model: str = "Cadangan",
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get(
            "HERMES_CUSTOM_LOCALHOST_20128_API_KEY", ""
        )
        self.model = model
        self.timeout = timeout

    def chat(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> ChatResponse:
        """Send a chat completion request (non-streaming)."""
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,  # OmniRoute defaults to SSE; force non-stream
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )

        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode())
            duration_ms = int((time.monotonic() - t0) * 1000)

            choice = body.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            usage = body.get("usage", {})

            return ChatResponse(
                content=content,
                model=body.get("model", model or self.model),
                provider_id="omniroute",
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                duration_ms=duration_ms,
            )
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:300]
            except Exception:
                pass
            return ChatResponse(
                content="", model=model or self.model, provider_id="omniroute",
                error=f"HTTP {e.code}: {detail}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as e:
            return ChatResponse(
                content="", model=model or self.model, provider_id="omniroute",
                error=str(e),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

    def ask(self, prompt: str, system: str = "Kamu adalah Argus, AI agent yang ringkas dan membantu.") -> ChatResponse:
        """One-shot Q&A convenience."""
        return self.chat(
            [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=prompt),
            ]
        )


def create_provider(
    base_url: str = "http://127.0.0.1:20128/v1",
    api_key: Optional[str] = None,
    model: str = "Cadangan",
    timeout: float = 120.0,
) -> OmniRouteProvider:
    return OmniRouteProvider(
        base_url=base_url, api_key=api_key, model=model, timeout=timeout
    )
