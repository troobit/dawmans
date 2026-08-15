"""The local and shared-backend providers (6.1, 6.2, 6.4, 6.14, 6.15).

The local provider's client is constructed against a loopback base URL
only, so 6.14's no-outbound-request property holds by construction —
asserted here with networking poisoned: every request a turn makes goes
through a transport that refuses any non-loopback host.

The shared backend is a stub behind the 6.15 disclosure gate: selecting
it records nothing, and a turn attempted before acknowledgement fails
pre-flight as provider-unconfigured / disclosure-unacknowledged.
"""

import asyncio
import inspect
import json

import httpx
import pytest

from dawmans.answer.envelope import Outcome, Reason
from dawmans.answer.outcome import GateState, pre_flight
from dawmans.answer.parse import FramingParser
from dawmans.answer.provider.anthropic import AnthropicProvider
from dawmans.answer.provider.base import (
    ProviderFailure,
    ProviderKind,
    SynthesisRequest,
    requires_key,
)
from dawmans.answer.provider.local import LOOPBACK_HOSTS, LocalProvider
from dawmans.answer.provider.shared import SharedBackendProvider

REQUEST = SynthesisRequest(
    system="You answer from supplied passages.",
    passages=({"passage_id": "ableton/live-12#4b12a1", "text": "The Track Activator mutes."},),
    question="Why is track 3 silent?",
)

SCRIPT = (
    "answered\n",
    "Turn the Track Activator back on. [[p:ableton/live-12#4b12a1]]\n",
    "---\n",
    "The `Track Activator` mutes the track output. [[p:ableton/live-12#4b12a1]]\n",
)


def collect(provider):
    async def run():
        return [delta async for delta in provider.stream(REQUEST)]

    return asyncio.run(run())


def _sse_body(deltas):
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": delta}}]})
        for delta in deltas
    ]
    lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode()


def poisoned_client(base_url, handler):
    """An httpx client whose transport refuses any non-loopback host."""

    def guarded(request):
        assert request.url.host in LOOPBACK_HOSTS, (
            f"outbound request escaped loopback: {request.url}"
        )
        return handler(request)

    return httpx.AsyncClient(base_url=base_url, transport=httpx.MockTransport(guarded))


def local_provider(deltas=SCRIPT, base_url="http://127.0.0.1:8080"):
    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(
            200, content=_sse_body(deltas), headers={"content-type": "text/event-stream"}
        )

    return LocalProvider(base_url, client=poisoned_client(base_url, handler))


# --- local: keyless is fully configured (6.4) --------------------------------


def test_local_requires_no_key_and_is_fully_configured():
    provider = local_provider()
    assert provider.kind is ProviderKind.LOCAL
    assert requires_key(provider.kind) is False
    status = provider.status()
    # A configured keyless provider is a valid, fully configured state:
    # nothing reports it as unconfigured or as missing a credential.
    assert status.configured is True
    assert status.masked is None
    gate = GateState(
        passage_count=100, selected_count=1,
        provider_kind=str(provider.kind), requires_key=requires_key(provider.kind),
        credential_stored=False,
    )
    assert pre_flight(gate) is None


def test_local_constructor_has_no_key_parameter():
    # 6.12: each provider constructs its own client against its own base
    # URL — there is no send-the-configured-key-to-the-configured-URL
    # path for a misconfiguration to redirect, structurally.
    parameters = inspect.signature(LocalProvider.__init__).parameters
    assert not any("key" in name for name in parameters)


# --- local: loopback by construction (6.14) ----------------------------------


@pytest.mark.parametrize(
    "base_url",
    ["http://example.com:8080", "http://192.168.1.20:8080", "https://api.anthropic.com"],
)
def test_non_loopback_base_url_is_refused_at_construction(base_url):
    with pytest.raises(ValueError):
        LocalProvider(base_url)


@pytest.mark.parametrize(
    "base_url",
    ["http://127.0.0.1:8080", "http://localhost:11434", "http://[::1]:1234"],
)
def test_loopback_base_urls_are_accepted(base_url):
    assert LocalProvider(base_url).status().configured is True


def test_whole_turn_makes_no_outbound_request():
    # The poisoned transport fails the test on any non-loopback host;
    # streaming a full turn and probing both stay on loopback.
    provider = local_provider()
    assert collect(provider) == list(SCRIPT)
    assert asyncio.run(provider.probe()).reachable is True


# --- local: rate-limit classification and the single retry (6.8) -------------


def _rate_limited_provider(responses, sleeps):
    """Responses are consumed in order; sleeps records the retry waits."""
    remaining = list(responses)

    def handler(request):
        return remaining.pop(0)

    async def sleep(seconds):
        sleeps.append(seconds)

    return LocalProvider(
        "http://127.0.0.1:8080",
        client=poisoned_client("http://127.0.0.1:8080", handler),
        sleep=sleep,
    )


def test_local_429_with_short_interval_retries_once_then_streams():
    sleeps = []
    ok = httpx.Response(
        200, content=_sse_body(SCRIPT), headers={"content-type": "text/event-stream"}
    )
    provider = _rate_limited_provider(
        [httpx.Response(429, headers={"retry-after": "1.4"}), ok], sleeps
    )
    assert collect(provider) == list(SCRIPT)
    # The stated interval was honoured as stated, unrounded.
    assert sleeps == [1.4]


def test_local_429_twice_surfaces_rate_limited_with_the_stated_interval():
    sleeps = []
    provider = _rate_limited_provider(
        [
            httpx.Response(429, headers={"retry-after": "1.4"}),
            httpx.Response(429, headers={"retry-after": "2.5"}),
        ],
        sleeps,
    )
    with pytest.raises(ProviderFailure) as exc:
        collect(provider)
    assert exc.value.kind == "rate-limited"
    assert exc.value.retry_after == 2.5  # unrounded, as the provider stated it
    assert sleeps == [1.4]  # retried exactly once


def test_local_429_with_no_stated_interval_does_not_retry_or_invent_one():
    sleeps = []
    provider = _rate_limited_provider([httpx.Response(429)], sleeps)
    with pytest.raises(ProviderFailure) as exc:
        collect(provider)
    assert exc.value.kind == "rate-limited"
    assert exc.value.retry_after is None
    assert sleeps == []


def test_local_429_with_interval_over_the_ceiling_surfaces_immediately():
    sleeps = []
    provider = _rate_limited_provider(
        [httpx.Response(429, headers={"retry-after": "3.4"})], sleeps
    )
    with pytest.raises(ProviderFailure) as exc:
        collect(provider)
    assert exc.value.kind == "rate-limited"
    assert exc.value.retry_after == 3.4
    assert sleeps == []


def test_local_connection_failure_raises_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    provider = LocalProvider(
        "http://127.0.0.1:8080",
        client=poisoned_client("http://127.0.0.1:8080", handler),
    )
    with pytest.raises(ProviderFailure) as exc:
        collect(provider)
    assert exc.value.kind == "unreachable"


# --- shared backend: the 6.15 gate -------------------------------------------


def test_selecting_the_shared_backend_records_nothing():
    provider = SharedBackendProvider()
    status = provider.status()
    assert status.requires_disclosure_ack is True
    assert status.configured is False


def test_turn_before_acknowledgement_fails_as_unconfigured():
    provider = SharedBackendProvider()
    gate = GateState(
        passage_count=100, selected_count=1,
        provider_kind=str(provider.kind), requires_key=requires_key(provider.kind),
        requires_ack=provider.requires_ack, acknowledged=provider.acknowledged,
    )
    classified = pre_flight(gate)
    assert classified is not None
    assert classified.outcome is Outcome.PROVIDER_UNCONFIGURED
    assert classified.reason is Reason.DISCLOSURE_UNACKNOWLEDGED
    # Defence in depth: the stub itself refuses to stream unacknowledged.
    with pytest.raises(ProviderFailure):
        collect(provider)


def test_acknowledgement_configures_the_shared_backend():
    provider = SharedBackendProvider()
    provider.acknowledge()
    status = provider.status()
    assert status.configured is True
    assert status.requires_disclosure_ack is False


def test_shared_probe_reports_the_stub_unreachable():
    provider = SharedBackendProvider()
    provider.acknowledge()
    assert asyncio.run(provider.probe()).reachable is False


# --- 6.2: one envelope shape for every provider ------------------------------


class _FakeStream:
    def __init__(self, script):
        self._script = script

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def deltas():
            for delta in self._script:
                yield delta

        return deltas()


class _FakeAnthropic:
    def __init__(self, script):
        outer = self

        class Messages:
            def stream(self, **kwargs):
                return _FakeStream(outer._script)

        self._script = script
        self.messages = Messages()


def test_same_scripted_stream_yields_the_same_envelope_for_all_three_kinds():
    # The one parser sits engine-side (Decision 4): streamed text,
    # citations and refusal signalling cannot vary by provider class.
    providers = (
        AnthropicProvider(api_key="sk-ant-test-1234", client=_FakeAnthropic(SCRIPT)),
        local_provider(SCRIPT),
        SharedBackendProvider(acknowledged=True, script=SCRIPT),
    )
    parsed = []
    for provider in providers:
        parser = FramingParser()
        for delta in collect(provider):
            parser.feed(delta)
        parsed.append(parser.result(covered=True))
    assert parsed[0] == parsed[1] == parsed[2]
    assert parsed[0].outcome is Outcome.ANSWERED
    assert parsed[0].framing == "parsed"
