"""The CI timing budgets over a synthetic 1,200-chunk index (4.2, 4.3).

4.2 (retrieval ≤ 10 ms median, ≤ 50 ms p95) and 4.3 (engine overhead
≤ 150 ms p95 with a stub provider) run here; the overhead cap excludes
retrieval and state acquisition, each measured against its own budget —
were either counted against it, the cap would be consumed before any
engine work began.

Honest limitations, mirrored from the design's §Timing: the query embed
is a stub (CI holds no model — the real ~2.2 ms embed is `make bench`'s),
and 4.1/4.6–4.8 need a real provider and a real index, so they are
`make bench` too, skipped when either is absent.
"""

import asyncio
import statistics
import time
from urllib.parse import quote

import numpy as np
import pytest
from corpus_fixtures import make_view, passage, triage_source, vendor_source
from http_fixtures import StubWatcher, get, make_app

from dawmans.answer.provider.base import ProbeResult, ProviderKind, ProviderStatus
from dawmans.answer.retrieve import retrieve
from dawmans.answer.state.null import NullStateSource
from dawmans.answer.turn import ProviderBinding, TurnPipeline

CHUNKS = 1200
DIM = 64

LIVE = "ableton/live-12"
APC = "akai/apc-key-25"
TRIAGE = "authored/triage"
ALL = (LIVE, APC, TRIAGE)


def p95(values):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


@pytest.fixture(scope="module")
def synthetic():
    """1,200 chunks across both source kinds, unit-norm random vectors and
    a real bm25s index over a generated vocabulary."""
    rng = np.random.default_rng(2026)
    vocabulary = np.array([f"term{i}" for i in range(400)] + ["filter", "resonance", "track"])
    counts = {LIVE: 1000, APC: 80, TRIAGE: 120}
    passages = []
    for source_id, count in counts.items():
        for position in range(count):
            words = " ".join(rng.choice(vocabulary, size=18))
            passages.append(passage(f"{source_id}#c{position:04d}", words))
    assert len(passages) == CHUNKS

    vectors = rng.standard_normal((CHUNKS, DIM)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    sources = [
        vendor_source(LIVE, LIVE, page_count=1009),
        vendor_source(APC, APC, page_count=5, status="assumed"),
        triage_source(),
    ]
    view = make_view(sources, passages, vectors=vectors)

    query = rng.standard_normal(DIM).astype(np.float32)
    query /= np.linalg.norm(query)
    return view, query


class TestRetrievalBudget:
    def test_median_at_most_10_ms_and_p95_at_most_50_ms(self, synthetic):
        view, query = synthetic
        question = "term12 term77 filter resonance on the track"
        retrieve(view, question, query, ALL)  # warm caches out of the measurement

        durations = []
        for _ in range(100):
            started = time.perf_counter()
            retrieve(view, question, query, ALL)
            durations.append((time.perf_counter() - started) * 1000.0)

        assert statistics.median(durations) <= 10.0
        assert p95(durations) <= 50.0


class TestFetchPassageBudget:
    def test_p95_at_most_50_ms_through_the_http_surface(self, synthetic):
        # 3.4: full text of a cited passage by identifier in under 50 ms
        # at p95 — measured through the route, not the bare dict lookup.
        view, _ = synthetic
        app = make_app(StubWatcher(view))
        path = "/passages/" + quote(f"{LIVE}#c0500", safe="/")
        assert get(app, path).status_code == 200  # warm out of the measurement

        durations = []
        for _ in range(100):
            started = time.perf_counter()
            response = get(app, path)
            durations.append((time.perf_counter() - started) * 1000.0)
            assert response.status_code == 200

        assert p95(durations) <= 50.0


SCRIPT = (
    "answered\n",
    f"Check the Track Activator first. [[p:{LIVE}#c0000]]\n",
    "---\n",
    f"The manual states the control mutes the output. [[p:{LIVE}#c0000]]\n",
    "1. Click the dimmed track number.\n",
)


class ScriptedProvider:
    kind = ProviderKind.LOCAL

    def status(self):
        return ProviderStatus(kind=self.kind, configured=True)

    async def probe(self):
        return ProbeResult(reachable=True)

    async def stream(self, req):
        for delta in SCRIPT:
            yield delta


class StubEmbedder:
    def __init__(self, vector):
        self.vector = vector

    def embed(self, texts):
        return [self.vector]


class TestEngineOverheadBudget:
    def test_p95_at_most_150_ms_with_each_excluded_stage_inside_its_own_budget(
        self, synthetic
    ):
        view, query = synthetic
        provider = ScriptedProvider()
        pipeline = TurnPipeline(
            watcher=StubWatcher(view),
            binding=lambda: ProviderBinding(
                provider=provider, kind=str(provider.kind), name="stub-local"
            ),
            state_source=NullStateSource(),
            embedder=StubEmbedder(query),
            count_tokens=lambda text: len(text.split()),
        )

        async def one_turn():
            timings = None
            async for event in pipeline.turn(
                "term12 term77 filter resonance on the track", sources=ALL
            ):
                if event.name == "timings":
                    timings = event.data
            assert timings is not None
            return timings

        collected = [asyncio.run(one_turn()) for _ in range(20)]

        # 4.3's cap, with retrieval and state acquisition excluded from it
        # and each held to its own budget instead (4.2, 4.4).
        assert p95([t.engine_overhead_ms for t in collected]) <= 150.0
        assert p95([t.retrieval_ms for t in collected]) <= 50.0
        assert p95([t.state_acquisition_ms for t in collected]) <= 100.0
