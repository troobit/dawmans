"""The keyed hosted provider over anthropic.AsyncAnthropic.

Settings per design §Anthropic provider specifics. Thinking is disabled
with effort low — this is a grounded extraction task, and thinking delays
the first text token, the only figure 4.6 measures. max_retries=0 keeps
6.8's retry-at-most-once enforceable; the 30 s / 2 s-connect timeout sits
above the engine's 10 s watchdog so ours fires first (4.9).

Verifying against the real API needs the Keychain key of
specs/api/answer-engine/prerequisites.md; nothing in CI does.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import anthropic
import httpx

from dawmans.answer.prompt import SYSTEM_PROMPT
from dawmans.answer.provider.base import (
    RETRY_AFTER_CEILING_S,
    ProbeResult,
    ProviderFailure,
    ProviderKind,
    ProviderStatus,
    SynthesisRequest,
    mask,
    user_text,
)

DEFAULT_MODEL = "claude-opus-5"

# Per-model prompt-cache minimums (claude-api skill). The ~600-token
# system prompt clears Opus 5's 512 only; the others silently lose the
# cache, which status() makes visible instead.
CACHE_MINIMUM_TOKENS = {
    "claude-opus-5": 512,
    "claude-sonnet-5": 1024,
    "claude-haiku-4-5": 4096,
}

# Output ceiling: 400 words is ~600 tokens; headroom so the framing's own
# word cap, not max_tokens, is what bounds an answer.
MAX_TOKENS = 1024


def _estimate_tokens(text: str) -> int:
    # Word-count estimate — the design's "~600-token" figure for the
    # system prompt. Only ever compared against the coarse cache minimums,
    # which sit far from the estimate on every configured model.
    return len(text.split())


def _retry_after(exc: anthropic.RateLimitError) -> float | None:
    stated = exc.response.headers.get("retry-after")
    if stated is None:
        return None
    try:
        return float(stated)
    except ValueError:
        return None


class AnthropicProvider:
    kind = ProviderKind.KEYED_HOSTED
    requires_ack = False

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        client: Any | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        # The client constructor is the full key's only reader (6.13);
        # everything else sees the masked form.
        self._masked = mask(api_key)
        self._model = model
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._client = (
            client
            if client is not None
            else anthropic.AsyncAnthropic(
                api_key=api_key,
                max_retries=0,
                timeout=httpx.Timeout(30.0, connect=2.0),
            )
        )

    def status(self) -> ProviderStatus:
        minimum = CACHE_MINIMUM_TOKENS.get(self._model)
        prompt_cache = None
        if minimum is not None:
            cleared = _estimate_tokens(SYSTEM_PROMPT) >= minimum
            prompt_cache = "available" if cleared else "unavailable"
        return ProviderStatus(
            kind=self.kind,
            configured=True,
            masked=self._masked,
            model=self._model,
            prompt_cache=prompt_cache,
        )

    async def probe(self) -> ProbeResult:
        try:
            await self._client.models.retrieve(self._model)
        except anthropic.APIConnectionError:
            return ProbeResult(reachable=False, detail="connection failed")
        except anthropic.APIStatusError as exc:
            return ProbeResult(reachable=False, detail=f"http {exc.response.status_code}")
        return ProbeResult(reachable=True)

    async def stream(self, req: SynthesisRequest) -> AsyncIterator[str]:
        kwargs = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "thinking": {"type": "disabled"},
            "output_config": {"effort": "low"},
            "system": [
                {
                    "type": "text",
                    "text": req.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": user_text(req)}],
        }
        yielded = False
        for attempt in (0, 1):
            try:
                async with self._client.messages.stream(**kwargs) as stream:
                    async for delta in stream.text_stream:
                        yielded = True
                        yield delta
                return
            except anthropic.RateLimitError as exc:
                stated = _retry_after(exc)
                # Retry only before any output: after a partial, a retry
                # would re-yield from the start and 6.10 owns the case.
                can_retry = attempt == 0 and not yielded
                if can_retry and stated is not None and stated <= RETRY_AFTER_CEILING_S:
                    await self._sleep(stated)
                    continue
                raise ProviderFailure(
                    "rate-limited", retry_after=stated, detail="rate limited (429)"
                ) from exc
            except anthropic.AuthenticationError as exc:
                # A key was present and the provider rejected it (6.6).
                raise ProviderFailure("auth", detail="authentication failed (401)") from exc
            except anthropic.APIConnectionError as exc:
                raise ProviderFailure("unreachable", detail="connection failed") from exc
            except anthropic.APIStatusError as exc:
                raise ProviderFailure(
                    "error", detail=f"provider error (http {exc.response.status_code})"
                ) from exc
