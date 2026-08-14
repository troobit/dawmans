"""OpenAI-compatible HTTP on loopback (llama.cpp, Ollama, LM Studio).

The client is constructed against a loopback base URL only — anything
else is refused at construction — so 6.14's no-outbound-request property
holds by construction rather than by discipline. requires_key is False:
a configured keyless provider is a fully configured state (6.4), and the
constructor has no key parameter at all (6.12).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from dawmans.answer.provider.base import (
    ProbeResult,
    ProviderFailure,
    ProviderKind,
    ProviderStatus,
    SynthesisRequest,
    user_text,
)

# 9.2's loopback set, applied to the provider's own base URL. httpx
# normalises `[::1]` to `::1` in url.host.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Above the engine's 10 s first-token watchdog (4.9), as for every kind.
_TIMEOUT = httpx.Timeout(30.0, connect=2.0)


class LocalProvider:
    kind = ProviderKind.LOCAL
    requires_ack = False

    def __init__(
        self,
        base_url: str,
        model: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        host = httpx.URL(base_url).host
        if host not in LOOPBACK_HOSTS:
            raise ValueError(
                f"local provider base URL must be loopback (6.14): {base_url!r}"
            )
        self._model = model
        self._client = (
            client
            if client is not None
            else httpx.AsyncClient(base_url=base_url, timeout=_TIMEOUT)
        )

    def status(self) -> ProviderStatus:
        # Keyless and fully configured: credential is None, and nothing
        # reports it as unconfigured or missing a credential (6.4).
        return ProviderStatus(
            kind=self.kind, configured=True, masked=None, model=self._model
        )

    async def probe(self) -> ProbeResult:
        try:
            response = await self._client.get("/v1/models")
        except httpx.TransportError:
            return ProbeResult(reachable=False, detail="connection failed")
        if response.status_code >= 400:
            return ProbeResult(reachable=False, detail=f"http {response.status_code}")
        return ProbeResult(reachable=True)

    async def stream(self, req: SynthesisRequest) -> AsyncIterator[str]:
        body = {
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": user_text(req)},
            ],
            "stream": True,
        }
        if self._model is not None:
            body["model"] = self._model
        try:
            async with self._client.stream(
                "POST", "/v1/chat/completions", json=body
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise ProviderFailure(
                        "error", detail=f"provider error (http {response.status_code})"
                    )
                async for line in response.aiter_lines():
                    delta = _delta_of(line)
                    if delta:
                        yield delta
        except httpx.TransportError as exc:
            raise ProviderFailure("unreachable", detail="connection failed") from exc


def _delta_of(line: str) -> str | None:
    """One SSE line of an OpenAI-compatible stream to its text delta."""
    if not line.startswith("data:"):
        return None
    payload = line[len("data:") :].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        chunk = json.loads(payload)
        return chunk["choices"][0]["delta"].get("content")
    except (json.JSONDecodeError, LookupError, AttributeError, TypeError):
        return None
