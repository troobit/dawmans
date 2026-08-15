"""The Anthropic provider (design §Anthropic provider specifics).

Settings are pinned so a drift fails a test: thinking disabled with
effort low, max_retries=0 — the SDK's default retries would apply their
own backoff inside the 10 s window and make 6.8's retry-at-most-once
unenforceable — and an httpx timeout of 30 s with 2 s connect so the
engine's watchdog fires first and attributes a stall to the provider.

CI runs against a scripted SDK. The live Keychain read and a real-key
call run on a developer machine only — see
specs/api/answer-engine/prerequisites.md.
"""

import asyncio

import anthropic
import httpx
import pytest

from dawmans.answer.provider.anthropic import (
    CACHE_MINIMUM_TOKENS,
    DEFAULT_MODEL,
    RETRY_AFTER_CEILING_S,
    AnthropicProvider,
)
from dawmans.answer.provider.base import (
    ProviderFailure,
    ProviderKind,
    SynthesisRequest,
    user_text,
)

KEY = "sk-ant-test-1234"

REQUEST = SynthesisRequest(
    system="You answer from supplied passages.",
    passages=({"passage_id": "ableton/live-12#a1", "text": "The Track Activator mutes."},),
    question="Why is track 3 silent?",
)


def _response(status, headers=None, text=""):
    return httpx.Response(
        status,
        headers=headers or {},
        text=text,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )


def rate_limit(retry_after=None):
    headers = {} if retry_after is None else {"retry-after": str(retry_after)}
    return anthropic.RateLimitError("rate limited", response=_response(429, headers), body=None)


class FakeStream:
    """The context manager messages.stream() returns, driving text_stream."""

    def __init__(self, script, mid_stream_failure=None):
        self._script = script
        self._mid_stream_failure = mid_stream_failure

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def deltas():
            for delta in self._script:
                yield delta
            if self._mid_stream_failure is not None:
                raise self._mid_stream_failure

        return deltas()


class FakeMessages:
    """Each attempt is either a FakeStream or an exception to raise."""

    def __init__(self, attempts):
        self._attempts = list(attempts)
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        attempt = self._attempts.pop(0)
        if isinstance(attempt, Exception):
            raise attempt
        return attempt


class FakeClient:
    def __init__(self, attempts):
        self.messages = FakeMessages(attempts)


def provider_for(attempts, **kwargs):
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    provider = AnthropicProvider(api_key=KEY, client=FakeClient(attempts), sleep=sleep, **kwargs)
    return provider, sleeps


def collect(provider):
    async def run():
        return [delta async for delta in provider.stream(REQUEST)]

    return asyncio.run(run())


# --- pinned client settings ---------------------------------------------------


def test_sdk_retries_are_off_and_timeouts_pinned():
    provider = AnthropicProvider(api_key=KEY)
    assert provider._client.max_retries == 0
    assert provider._client.timeout == httpx.Timeout(30.0, connect=2.0)


def test_default_model_and_kind():
    provider = AnthropicProvider(api_key=KEY)
    assert provider.kind is ProviderKind.KEYED_HOSTED
    assert provider.status().model == DEFAULT_MODEL == "claude-opus-5"


def test_request_shape_thinking_disabled_effort_low_cached_system():
    provider, _ = provider_for([FakeStream(["ok"])])
    collect(provider)
    (call,) = provider._client.messages.calls
    assert call["model"] == DEFAULT_MODEL
    assert call["thinking"] == {"type": "disabled"}
    assert call["output_config"] == {"effort": "low"}
    # cache_control on the last system block (design cache ordering); the
    # varying half sits after the breakpoint in the one user turn.
    assert call["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert call["system"][-1]["text"] == REQUEST.system
    assert call["messages"] == [{"role": "user", "content": user_text(REQUEST)}]


# --- deltas -------------------------------------------------------------------


def test_deltas_stream_via_text_stream():
    provider, _ = provider_for([FakeStream(["The ", "Track ", "Activator"])])
    assert collect(provider) == ["The ", "Track ", "Activator"]


# --- rate-limit policy (6.8) --------------------------------------------------


def test_429_with_small_retry_after_sleeps_it_and_retries_once():
    provider, sleeps = provider_for([rate_limit("2"), FakeStream(["ok"])])
    assert collect(provider) == ["ok"]
    assert sleeps == [2.0]
    assert len(provider._client.messages.calls) == 2


def test_retry_after_is_honoured_unrounded_on_the_retry_branch():
    provider, sleeps = provider_for([rate_limit("2.6"), FakeStream(["ok"])])
    collect(provider)
    assert sleeps == [2.6]


def test_429_over_ceiling_surfaces_unrounded_without_retrying():
    # 3.4 rounded before the comparison would change which branch runs.
    assert RETRY_AFTER_CEILING_S == 3.0
    provider, sleeps = provider_for([rate_limit("3.4")])
    with pytest.raises(ProviderFailure) as exc:
        collect(provider)
    assert exc.value.kind == "rate-limited"
    assert exc.value.retry_after == 3.4
    assert sleeps == []
    assert len(provider._client.messages.calls) == 1


def test_second_429_surfaces_after_the_single_retry():
    provider, sleeps = provider_for([rate_limit("1"), rate_limit("2.5")])
    with pytest.raises(ProviderFailure) as exc:
        collect(provider)
    assert exc.value.kind == "rate-limited"
    assert exc.value.retry_after == 2.5
    assert sleeps == [1.0]


def test_429_with_no_stated_interval_surfaces_with_absent_retry_after():
    # Nothing is invented (6.8): no stated interval, nothing to honour.
    provider, sleeps = provider_for([rate_limit(None)])
    with pytest.raises(ProviderFailure) as exc:
        collect(provider)
    assert exc.value.kind == "rate-limited"
    assert exc.value.retry_after is None
    assert sleeps == []


def test_no_retry_after_partial_output():
    # A retry after streamed output would re-yield from the start; the
    # engine classifies a mid-stream failure as incomplete (6.10).
    provider, sleeps = provider_for([FakeStream(["part"], rate_limit("1"))])

    async def run():
        seen = []
        with pytest.raises(ProviderFailure):
            async for delta in provider.stream(REQUEST):
                seen.append(delta)
        return seen

    assert asyncio.run(run()) == ["part"]
    assert sleeps == []
    assert len(provider._client.messages.calls) == 1


# --- prompt cache visibility --------------------------------------------------


def test_cache_minimums_per_model():
    assert CACHE_MINIMUM_TOKENS == {
        "claude-opus-5": 512,
        "claude-sonnet-5": 1024,
        "claude-haiku-4-5": 4096,
    }


def test_opus_clears_its_cache_minimum():
    provider = AnthropicProvider(api_key=KEY, model="claude-opus-5")
    assert provider.status().prompt_cache == "available"


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-haiku-4-5"])
def test_models_whose_minimum_the_prompt_misses_report_unavailable(model):
    # Selecting these silently loses the cache; status makes it visible.
    provider = AnthropicProvider(api_key=KEY, model=model)
    assert provider.status().prompt_cache == "unavailable"


# --- failure kinds (6.6, 6.7) -------------------------------------------------


def test_connection_error_raises_the_unreachable_kind():
    error = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    provider, _ = provider_for([error])
    with pytest.raises(ProviderFailure) as exc:
        collect(provider)
    assert exc.value.kind == "unreachable"


def test_401_with_a_key_present_raises_the_auth_kind():
    # Feeds 6.6: distinguishable from missing-credential by the sub-code.
    error = anthropic.AuthenticationError(
        "bad key", response=_response(401, text="secret payload"), body=None
    )
    provider, _ = provider_for([error])
    with pytest.raises(ProviderFailure) as exc:
        collect(provider)
    assert exc.value.kind == "auth"


def test_other_status_errors_raise_the_error_kind():
    error = anthropic.InternalServerError(
        "boom", response=_response(500, text="raw provider payload"), body=None
    )
    provider, _ = provider_for([error])
    with pytest.raises(ProviderFailure) as exc:
        collect(provider)
    assert exc.value.kind == "error"
    # detail is the engine's wording, never a raw provider payload.
    assert "raw provider payload" not in (exc.value.detail or "")


# --- status and probe ---------------------------------------------------------


def test_status_is_configured_and_masked_only():
    status = AnthropicProvider(api_key=KEY).status()
    assert status.configured is True
    assert status.masked == "…1234"
    assert KEY not in repr(status)


def test_probe_reports_reachability_without_synthesis():
    class Models:
        def __init__(self, error=None):
            self._error = error
            self.retrieved = []

        async def retrieve(self, model):
            self.retrieved.append(model)
            if self._error is not None:
                raise self._error
            return object()

    reachable = AnthropicProvider(api_key=KEY, client=FakeClient([]))
    reachable._client.models = Models()
    result = asyncio.run(reachable.probe())
    assert result.reachable is True
    assert reachable._client.messages.calls == []  # no synthesis

    down = AnthropicProvider(api_key=KEY, client=FakeClient([]))
    down._client.models = Models(
        anthropic.APIConnectionError(
            request=httpx.Request("GET", "https://api.anthropic.com/v1/models")
        )
    )
    assert asyncio.run(down.probe()).reachable is False
