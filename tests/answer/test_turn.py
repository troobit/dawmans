"""The turn pipeline (design §Architecture, §The outcome procedure, 9.13).

Providers are stubbed with scripted streams, so every path except the
network is deterministic. The concurrency test is the one place real time
is measured: retrieval is synchronous numpy work, so only `asyncio.to_thread`
makes the state task genuinely run alongside it — a bare coroutine would
serialise the two and the wall-clock assertion would fail.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime

import numpy as np
from corpus_fixtures import make_view, passage, sidecar_entry, triage_source, vendor_source
from hypothesis import given, settings
from hypothesis import strategies as st

from dawmans.answer.envelope import (
    Cause,
    Citation,
    Narrowing,
    Outcome,
    Reason,
    SourceRef,
    Timings,
)
from dawmans.answer.provider.base import ProviderFailure, ProviderKind, ProviderStatus
from dawmans.answer.state.base import StateSnapshot
from dawmans.answer.state.null import NullStateSource
from dawmans.answer.turn import ProviderBinding, TurnPipeline

LIVE = "ableton/live-12"
APC = "akai/apc-key-25"
TRIAGE = "authored/triage"

SOURCES = [
    vendor_source(LIVE, LIVE, page_count=1009),
    vendor_source(APC, APC, page_count=5),
    triage_source(),
]

# Row order: LIVE#p1, LIVE#p2, APC#p1, TRIAGE#t1 — one-hot vectors, so a
# test states every cosine directly in the query vector its embedder returns.
PASSAGES = [
    passage(f"{LIVE}#p1", "The Track Activator mutes the track output"),
    passage(f"{LIVE}#p2", "Click the dimmed track number to re-enable the track"),
    passage(f"{APC}#p1", "Hold SHIFT and press a pad to select a scene"),
    passage(f"{TRIAGE}#t1", "No sound from a track although the meters move"),
]

ENTRY = sidecar_entry(
    f"{TRIAGE}#t1",
    [LIVE],
    symptom="No sound from a track",
    causes=[
        {
            "statement": "The Track Activator is off",
            "check": "the track number is dimmed in the mixer",
            "fix": [{"source_id": LIVE, "section": "16.4", "passage_ids": [f"{LIVE}#p2"]}],
            "undocumented_device": None,
            "flags": [],
        },
        {
            "statement": "The scene is not launched",
            "check": "no pad is lit on the controller",
            "fix": [{"source_id": APC, "section": "3.1", "passage_ids": [f"{APC}#p1"]}],
            "undocumented_device": None,
            "flags": [],
        },
    ],
)

ALL = (LIVE, APC, TRIAGE)

# Cosines put LIVE#p1 and APC#p1 over τ — a question spanning both sources.
Q_BOTH = np.array([0.8, 0.0, 0.9, 0.0], dtype=np.float32)
# The triage entry leads, with the Live manual's activator passage beside it.
Q_TRIAGE = np.array([0.5, 0.0, 0.0, 0.9], dtype=np.float32)

ANSWERED_SCRIPT = (
    "answered\n",
    f"Turn the Track Activator back on. [[p:{LIVE}#p1]]\n",
    "---\n",
    "## Why\n",
    f"The `Track Activator` mutes the track output. [[p:{LIVE}#p1]]\n",
    "\n",
    f"1. Hold SHIFT and press the pad. [[p:{APC}#p1]]\n",
    "~uncovered whether direct monitoring is also muted\n",
)


def make_watcher(view):
    class _Watcher:
        def __init__(self):
            self.view = view
            self.corpus_reload_ms = None
            self._pending = None

        def swap(self, next_view):
            self._pending = next_view

        def check(self):
            if self._pending is not None:
                self.view = self._pending
                self._pending = None

    return _Watcher()


class StubEmbedder:
    """Returns a fixed query vector; optionally blocks synchronously, the
    way real numpy/BGE work does, to expose a serialised gather."""

    def __init__(self, vector, *, block_s=0.0):
        self.vector = vector
        self.block_s = block_s

    def embed(self, texts):
        if self.block_s:
            time.sleep(self.block_s)
        return [np.asarray(self.vector, dtype=np.float32)]


class ScriptedProvider:
    kind = ProviderKind.LOCAL

    def __init__(
        self, script=ANSWERED_SCRIPT, *, delay_s=0.0, fail=None, stall=False, endless=False
    ):
        self.script = script
        self.delay_s = delay_s
        self.fail = fail  # ProviderFailure raised after the script
        self.stall = stall  # never yields — the watchdog's case
        self.endless = endless
        self.requests = []
        self.closed = False
        self.closed_at = None

    def status(self):
        return ProviderStatus(kind=self.kind, configured=True)

    async def probe(self):
        raise NotImplementedError

    async def stream(self, req):
        self.requests.append(req)
        try:
            if self.stall:
                await asyncio.sleep(3600)
            for delta in self.script:
                if self.delay_s:
                    await asyncio.sleep(self.delay_s)
                yield delta
            while self.endless:
                await asyncio.sleep(0)
                yield "more body text follows here\n"
            if self.fail is not None:
                raise self.fail
        finally:
            self.closed = True
            self.closed_at = time.perf_counter()


def binding_for(provider, *, name="stub-local"):
    return ProviderBinding(provider=provider, kind=str(provider.kind), name=name)


def make_pipeline(
    provider=None,
    *,
    view=None,
    watcher=None,
    query=Q_BOTH,
    state=None,
    binding=None,
    block_s=0.0,
    first_token_timeout=10.0,
    state_timeout=0.100,
):
    if view is None:
        view = make_view(SOURCES, PASSAGES, sidecar=[ENTRY])
    watcher = watcher or make_watcher(view)
    provider = provider or ScriptedProvider()
    pipeline = TurnPipeline(
        watcher=watcher,
        binding=binding or (lambda: binding_for(provider)),
        state_source=state or NullStateSource(),
        embedder=StubEmbedder(query, block_s=block_s),
        count_tokens=lambda text: len(text.split()),
        first_token_timeout=first_token_timeout,
        state_timeout=state_timeout,
    )
    return pipeline, provider, watcher


async def collect(events):
    return [event async for event in events]


def run_turn(pipeline, question="why is track 3 silent", **kwargs):
    return asyncio.run(collect(pipeline.turn(question, **kwargs)))


def names(events):
    return [event.name for event in events]


def only(events, name):
    matched = [event.data for event in events if event.name == name]
    assert len(matched) == 1, f"expected one {name} event, saw {len(matched)}"
    return matched[0]


def each(events, name):
    return [event.data for event in events if event.name == name]


class TestConcurrency:
    def test_retrieval_and_state_are_gathered_not_serialised(self):
        # Retrieval blocks a thread for 60 ms while the state source sleeps
        # 60 ms of loop time; run concurrently the stage costs ~60 ms, run
        # serially ≥120 ms. The margin is wide enough not to flake.
        class SlowState:
            origin = "slow"

            async def snapshot(self):
                await asyncio.sleep(0.06)
                return StateSnapshot(values=(), acquired_at=datetime.now(UTC))

        pipeline, _, _ = make_pipeline(state=SlowState(), block_s=0.06)
        started = time.perf_counter()
        events = run_turn(pipeline, sources=ALL)
        elapsed = time.perf_counter() - started
        assert only(events, "outcome").outcome is Outcome.ANSWERED
        assert elapsed < 0.115, f"gather looks serialised: {elapsed:.3f}s"


class TestStateDegradation:
    def _turn_with_state(self, state, caplog, state_timeout=0.100):
        pipeline, provider, _ = make_pipeline(state=state, state_timeout=state_timeout)
        with caplog.at_level(logging.INFO, logger="dawmans.answer.turn"):
            events = run_turn(pipeline, sources=ALL)
        return events, provider

    def test_state_timeout_degrades_to_manual_only_with_a_note(self, caplog):
        class Stuck:
            origin = "stuck"

            async def snapshot(self):
                await asyncio.sleep(3600)

        events, provider = self._turn_with_state(Stuck(), caplog, state_timeout=0.02)
        assert only(events, "outcome").outcome is Outcome.ANSWERED
        [request] = provider.requests
        assert request.state is None
        assert any("state" in record.getMessage().lower() for record in caplog.records)

    def test_state_failure_never_fails_the_turn(self, caplog):
        class Broken:
            origin = "broken"

            async def snapshot(self):
                raise RuntimeError("log file vanished")

        events, provider = self._turn_with_state(Broken(), caplog)
        assert only(events, "outcome").outcome is Outcome.ANSWERED
        assert provider.requests[0].state is None

    def test_malformed_snapshot_degrades_like_a_failure(self, caplog):
        class Malformed:
            origin = "malformed"

            async def snapshot(self):
                return StateSnapshot(values=(object(),), acquired_at=datetime.now(UTC))

        events, provider = self._turn_with_state(Malformed(), caplog)
        assert only(events, "outcome").outcome is Outcome.ANSWERED
        assert provider.requests[0].state is None

    def test_null_source_answers_without_degradation(self):
        # 8.2/8.3: with the null source nothing is noted, nothing enters
        # the prompt, and the turn is the ordinary answered turn.
        pipeline, provider, _ = make_pipeline(state=NullStateSource())
        events = run_turn(pipeline, sources=ALL)
        assert only(events, "outcome").outcome is Outcome.ANSWERED
        assert "Session state" not in provider.requests[0].user
        assert only(events, "framing") == "parsed"
        assert {citation.source_id for citation in each(events, "citation")} == {LIVE, APC}


class TestWatchdogAndCancellation:
    def test_no_first_token_within_the_window_abandons_naming_the_provider(self):
        provider = ScriptedProvider(stall=True)
        pipeline, _, _ = make_pipeline(
            provider,
            binding=lambda: binding_for(provider, name="stub-local"),
            first_token_timeout=0.02,
        )
        events = run_turn(pipeline, sources=ALL)
        classified = only(events, "outcome")
        assert classified.outcome is Outcome.TIMEOUT
        assert "stub-local" in classified.detail
        assert names(events)[-1] == "done"
        assert provider.closed  # released, not left draining

    def test_superseding_cancels_within_the_release_bound(self):
        # 9.13 + 4.10: a new question on the same conversation cancels the
        # in-flight turn; the provider stream is closed — not drained —
        # within 250 ms.
        async def scenario():
            provider = ScriptedProvider(delay_s=0.01, endless=True)
            current = {"provider": provider}
            pipeline, _, _ = make_pipeline(
                provider, binding=lambda: binding_for(current["provider"])
            )
            conversation = pipeline.conversations.get(None)
            first = pipeline.turn(
                "why is track 3 silent", sources=ALL, conversation_id=conversation.id
            )
            first_events = []

            async def consume_first():
                async for event in first:
                    first_events.append(event)

            task = asyncio.create_task(consume_first())
            while len(first_events) < 3:
                await asyncio.sleep(0.005)
            current["provider"] = ScriptedProvider()  # the new turn must finish
            superseded_at = time.perf_counter()
            second_events = await collect(
                pipeline.turn("a new question", conversation_id=conversation.id)
            )
            await task
            return provider, first_events, second_events, superseded_at

        provider, first_events, second_events, superseded_at = asyncio.run(scenario())
        assert provider.closed_at - superseded_at < 0.25
        assert names(first_events)[-2:] == ["outcome", "done"]
        cancelled = [e.data for e in first_events if e.name == "outcome"][-1]
        assert cancelled.outcome is Outcome.CANCELLED
        outcomes = [e.data for e in second_events if e.name == "outcome"]
        assert outcomes[-1].outcome is Outcome.ANSWERED

    def test_no_interleaving_between_the_old_stream_and_the_new(self):
        async def scenario():
            provider = ScriptedProvider(delay_s=0.005, endless=True)
            current = {"provider": provider}
            pipeline, _, _ = make_pipeline(
                provider, binding=lambda: binding_for(current["provider"])
            )
            conversation = pipeline.conversations.get(None)
            log = []

            async def consume(label, turn):
                async for event in turn:
                    log.append((label, event.name))

            first = asyncio.create_task(
                consume(
                    "old",
                    pipeline.turn(
                        "why is track 3 silent", sources=ALL, conversation_id=conversation.id
                    ),
                )
            )
            while len(log) < 3:
                await asyncio.sleep(0.005)
            current["provider"] = ScriptedProvider()  # the new turn must finish
            await consume("new", pipeline.turn("a new question", conversation_id=conversation.id))
            await first
            return log

        log = asyncio.run(scenario())
        first_new = next(index for index, (label, _) in enumerate(log) if label == "new")
        assert all(label == "new" for label, _ in log[first_new:])
        old_names = [name for label, name in log if label == "old"]
        assert old_names[-2:] == ["outcome", "done"]

    @settings(max_examples=20, deadline=None)
    @given(prefix=st.integers(min_value=0, max_value=12))
    def test_cancelling_any_prefix_yields_cancelled_and_nothing_after_done(self, prefix):
        # The cancellation property: for any stream prefix, cancelling
        # yields cancelled, retains the partial already emitted, and emits
        # nothing after done.
        async def scenario():
            provider = ScriptedProvider(endless=True)
            current = {"provider": provider}
            pipeline, _, _ = make_pipeline(
                provider, binding=lambda: binding_for(current["provider"])
            )
            conversation = pipeline.conversations.get(None)
            first = pipeline.turn(
                "why is track 3 silent", sources=ALL, conversation_id=conversation.id
            )
            events = []

            async def consume():
                async for event in first:
                    events.append(event)

            task = asyncio.create_task(consume())
            while len(events) < prefix:
                await asyncio.sleep(0)
            current["provider"] = ScriptedProvider()  # the new turn must finish
            await collect(pipeline.turn("a new question", conversation_id=conversation.id))
            await task
            return events

        events = asyncio.run(scenario())
        assert names(events).count("done") == 1
        assert names(events)[-1] == "done"
        final = [event.data for event in events if event.name == "outcome"][-1]
        assert final.outcome is Outcome.CANCELLED


class TestProviderSeam:
    def test_a_provider_change_applies_to_the_next_turn_without_restart(self):
        # 6.3: the binding is read at turn start; the view and its
        # retrieval state are untouched by the change.
        first, second = ScriptedProvider(), ScriptedProvider()
        current = {"provider": first}
        pipeline, _, watcher = make_pipeline(
            first, binding=lambda: binding_for(current["provider"])
        )
        view_before = watcher.view
        conversation = pipeline.conversations.get(None)
        run_turn(pipeline, sources=ALL, conversation_id=conversation.id)
        current["provider"] = second
        run_turn(pipeline, "and the return track?", conversation_id=conversation.id)
        assert len(first.requests) == 1
        assert len(second.requests) == 1
        assert watcher.view is view_before

    def test_no_provider_configured_fails_the_turn_but_not_the_view(self):
        pipeline, _, watcher = make_pipeline(
            binding=lambda: ProviderBinding(provider=None, kind=None)
        )
        events = run_turn(pipeline, sources=ALL)
        classified = only(events, "outcome")
        assert classified.outcome is Outcome.PROVIDER_UNCONFIGURED
        assert classified.reason is Reason.NO_PROVIDER_KIND
        # 6.5: retrieval-only operations still work — the loaded view
        # resolves a passage lookup after the failed turn.
        assert watcher.view.passages_by_id[f"{LIVE}#p1"]["text"]

    def test_a_provider_error_substitutes_nothing(self):
        # 6.9: no synthesised answer, no cached answer — there is no answer
        # cache at all. The failed turn carries no answer events, and the
        # next turn's answer comes from its own provider stream.
        failing = ScriptedProvider(script=(), fail=ProviderFailure("error", detail="boom"))
        current = {"provider": failing}
        pipeline, _, _ = make_pipeline(failing, binding=lambda: binding_for(current["provider"]))
        failed = run_turn(pipeline, sources=ALL)
        classified = only(failed, "outcome")
        assert classified.outcome is Outcome.PROVIDER_ERROR
        assert classified.reason is Reason.PROVIDER_REJECTED
        assert each(failed, "direct_answer") == []
        assert each(failed, "body_delta") == []
        current["provider"] = working = ScriptedProvider()
        answered = run_turn(pipeline, sources=ALL)
        assert only(answered, "direct_answer").startswith("Turn the Track Activator")
        assert len(working.requests) == 1

    def test_a_mid_stream_failure_marks_incomplete_and_retains_the_partial(self):
        provider = ScriptedProvider(
            script=ANSWERED_SCRIPT[:5], fail=ProviderFailure("error", detail="died")
        )
        pipeline, _, _ = make_pipeline(provider)
        events = run_turn(pipeline, sources=ALL)
        outcomes = [event.data for event in events if event.name == "outcome"]
        assert outcomes[0].outcome is Outcome.ANSWERED
        assert outcomes[-1].outcome is Outcome.INCOMPLETE
        assert only(events, "direct_answer").startswith("Turn the Track Activator")
        assert names(events)[-1] == "done"


class TestEnvelopeAssembly:
    def test_a_cross_source_question_cites_both_with_the_small_guide_present(self):
        # 5.7 with 5.6's floor: the APC guide qualifies, reaches synthesis,
        # and the one answer cites both sources.
        pipeline, provider, _ = make_pipeline()
        events = run_turn(pipeline, sources=ALL)
        supplied_ids = [record["passage_id"] for record in provider.requests[0].passages]
        assert f"{APC}#p1" in supplied_ids
        cited = {citation.source_id for citation in each(events, "citation")}
        assert cited == {LIVE, APC}
        assert all(isinstance(citation, Citation) for citation in each(events, "citation"))

    def test_contributing_sources_is_supplied_derived_never_citation_derived(self):
        # The script cites only the Live manual; the APC guide still
        # supplied a passage, so it is reported (5.9, CONTRACTS §4).
        live_only = (
            "answered\n",
            f"Turn the Track Activator back on. [[p:{LIVE}#p1]]\n",
            "---\n",
            f"The `Track Activator` mutes the track output. [[p:{LIVE}#p1]]\n",
        )
        pipeline, provider, _ = make_pipeline(ScriptedProvider(script=live_only))
        events = run_turn(pipeline, sources=ALL)
        contributing = only(events, "contributing_sources")
        supplied = {record["source_id"] for record in provider.requests[0].passages}
        assert set(contributing) == supplied
        assert APC in contributing
        cited = {citation.source_id for citation in each(events, "citation")}
        assert cited == {LIVE}

    def test_unresolvable_markers_are_stripped_from_the_stream(self):
        script = (
            "answered\n",
            f"Turn it on. [[p:{LIVE}#p1]] [[p:invented/source#zz]]\n",
            "---\n",
            "A paragraph citing something fabricated. [[p:invented/source#zz]]\n",
        )
        pipeline, _, _ = make_pipeline(ScriptedProvider(script=script))
        events = run_turn(pipeline, sources=ALL)
        assert "[[p:invented" not in only(events, "direct_answer")
        assert f"[[p:{LIVE}#p1]]" in only(events, "direct_answer")
        assert not any("[[p:invented" in delta for delta in each(events, "body_delta"))

    def test_hoisted_sigils_never_reach_body_deltas(self):
        pipeline, _, _ = make_pipeline()
        events = run_turn(pipeline, sources=ALL)
        body = "".join(each(events, "body_delta"))
        assert "~uncovered" not in body
        assert only(events, "uncovered_parts") == ("whether direct monitoring is also muted",)

    def test_timings_carries_durations_only_for_the_five_stages(self):
        pipeline, _, _ = make_pipeline()
        events = run_turn(pipeline, sources=ALL)
        timings = only(events, "timings")
        assert isinstance(timings, Timings)
        for stage in (
            "retrieval_ms",
            "state_acquisition_ms",
            "engine_overhead_ms",
            "first_token_ms",
            "completion_ms",
        ):
            value = getattr(timings, stage)
            assert isinstance(value, float) and value >= 0.0
        assert names(events)[0] == "outcome"
        assert names(events)[-1] == "done"
        assert only(events, "done") == {"complete": True}

    def test_an_unknown_selected_source_id_is_identified(self):
        pipeline, provider, _ = make_pipeline()
        events = run_turn(pipeline, sources=(LIVE, "nord/stage-4"))
        classified = only(events, "outcome")
        assert classified.outcome is Outcome.UNKNOWN_SOURCE_ID
        assert "nord/stage-4" in classified.detail
        assert provider.requests == []


class TestNarrowingPath:
    def test_entry_path_narrowing_is_engine_built_from_the_sidecar(self):
        script = (
            "needs-narrowing\n",
            "Check which of these you can observe first.\n",
            "---\n",
            f"The entry ranks two causes. [[p:{TRIAGE}#t1]]\n",
        )
        pipeline, provider, _ = make_pipeline(ScriptedProvider(script=script), query=Q_TRIAGE)
        events = run_turn(pipeline, "no sound from track 3", sources=ALL)
        narrowing = only(events, "narrowing")
        assert isinstance(narrowing, Narrowing)
        assert [candidate.label for candidate in narrowing.candidates] == [
            "the track number is dimmed in the mixer",
            "no pad is lit on the controller",
        ]
        # The expansion put the causes' fix passages in supplied (7.2).
        supplied_ids = {record["passage_id"] for record in provider.requests[0].passages}
        assert {f"{LIVE}#p2", f"{APC}#p1"} <= supplied_ids

    def test_ranked_causes_at_the_limit_is_engine_built_and_cited(self):
        script = (
            "ranked-causes\n",
            "Look for a dimmed track number in the mixer.\n",
            "---\n",
            f"Two candidates remain. [[p:{TRIAGE}#t1]]\n",
        )
        pipeline, provider, watcher = make_pipeline(ScriptedProvider(script=script), query=Q_TRIAGE)
        conversation = pipeline.conversations.get(None)
        conversation.set_scope(ALL, watcher.view)
        conversation.record_turn("no sound from track 3", Outcome.NEEDS_NARROWING, "Which?")
        conversation.record_turn("neither", Outcome.NEEDS_NARROWING, "Then which?")
        events = run_turn(pipeline, "still neither", conversation_id=conversation.id)
        causes = each(events, "cause")
        assert [cause.rank for cause in causes] == [1, 2]
        assert all(isinstance(cause, Cause) for cause in causes)
        assert causes[0].statement == "The Track Activator is off"
        assert causes[0].fix_cites == (f"{LIVE}#p2",)
        # 7.6: every cited id resolves into the turn's citations[].
        cited = {citation.passage_id for citation in each(events, "citation")}
        for cause in causes:
            assert set(cause.cites) <= cited
            assert set(cause.fix_cites) <= cited
        # The prompt carried the terminal direction (7.5's mechanism).
        assert "Narrowing limit reached" in provider.requests[0].user
        assert conversation.narrowing_count == 0
        # 7.6: direct_answer is engine-built — the rank-1 cause's check
        # stated as an instruction, never the model's line 2 and never
        # an assertion of the cause.
        assert only(events, "direct_answer") == (
            "Check whether the track number is dimmed in the mixer."
        )


class TestSuggestionScope:
    def test_a_suggested_source_already_in_scope_is_dropped(self):
        # 2.3: suggestions are unselected sources only. The model names
        # one selected and one unselected source; only the unselected one
        # reaches suggested_sources[].
        script = (
            "refused-not-covered\n",
            "The selected source does not cover this question.\n",
            "---\n",
            f"!suggest {LIVE}\n",
            f"!suggest {APC}\n",
        )
        pipeline, _, _ = make_pipeline(ScriptedProvider(script=script))
        events = run_turn(pipeline, sources=(LIVE,))
        assert only(events, "suggested_sources") == (SourceRef(source_id=APC, display_name=APC),)


class TestUncoveredRetrieval:
    def test_below_threshold_retrieval_supplies_no_passages(self):
        # 2.7: nothing above the threshold means nothing is supplied to
        # synthesis — the prompt-directed refusal is the model's only
        # grounded move, and no weak match exists to synthesise from.
        script = (
            "refused-not-covered\n",
            "The selected sources do not cover this question.\n",
            "---\n",
            "None of the selected sources describes this.\n",
        )
        pipeline, provider, _ = make_pipeline(
            ScriptedProvider(script=script),
            query=np.zeros(4, dtype=np.float32),
        )
        events = run_turn(pipeline, "flumph gargle wibble", sources=ALL)
        assert provider.requests[0].passages == ()
        assert only(events, "outcome").outcome is Outcome.REFUSED_NOT_COVERED
        assert only(events, "contributing_sources") == ()
        assert each(events, "citation") == []

    def test_an_explicitly_empty_selection_declines_without_a_provider_call(self):
        # 5.2's primary branch: sources=() submitted, not merely pruned to
        # empty — the turn declines and never falls back to all sources.
        pipeline, provider, _ = make_pipeline()
        events = run_turn(pipeline, sources=())
        assert only(events, "outcome").outcome is Outcome.NO_SOURCES_SELECTED
        assert provider.requests == []
        assert names(events) == ["outcome", "done"]


class TestScopeAtTurnTime:
    def test_a_removed_source_drops_with_a_scope_dropped_event(self):
        pipeline, _, watcher = make_pipeline()
        conversation = pipeline.conversations.get(None)
        first = run_turn(pipeline, sources=ALL, conversation_id=conversation.id)
        assert each(first, "scope_dropped") == []

        shrunk = make_view([SOURCES[0]], PASSAGES[:2], vectors=np.eye(4, dtype=np.float32)[:2])
        watcher.swap(shrunk)
        second = run_turn(pipeline, "and now?", conversation_id=conversation.id)
        dropped = only(second, "scope_dropped")
        assert set(dropped) == {
            SourceRef(source_id=APC, display_name=APC),
            SourceRef(source_id=TRIAGE, display_name="Symptom triage entries"),
        }
        assert names(second).index("scope_dropped") < names(second).index("outcome")
        outcomes = [event.data for event in second if event.name == "outcome"]
        assert outcomes[0].outcome is Outcome.ANSWERED  # answers from what remains

    def test_pruning_the_last_source_yields_no_sources_selected(self):
        view = make_view([SOURCES[2]], [PASSAGES[3]], sidecar=[ENTRY])
        pipeline, _, watcher = make_pipeline(view=view, query=np.array([1.0], dtype=np.float32))
        conversation = pipeline.conversations.get(None)
        run_turn(pipeline, sources=(TRIAGE,), conversation_id=conversation.id)
        watcher.swap(make_view([SOURCES[0]], PASSAGES[:2]))
        events = run_turn(pipeline, "and now?", conversation_id=conversation.id)
        assert only(events, "scope_dropped") != ()
        assert only(events, "outcome").outcome is Outcome.NO_SOURCES_SELECTED
