"""The turn pipeline (design §Architecture; pinned here by §Module placement).

One turn is one async generator of CONTRACTS §4b events: the gates, the
retrieval-and-state gather, prompt assembly, the provider call with the
first-token watchdog and cancellation, the incremental parser pass, the
grounding check, and timings.

Two structural points carry the design:

- Retrieval is synchronous numpy and bm25s work, so it runs under
  `asyncio.to_thread` gathered with `StateSource.snapshot` under
  `wait_for(0.100)` — a bare coroutine would never yield, the state task
  would not be scheduled, and the timeout could not fire (4.4, 8.9).
- One in-flight turn per conversation (9.13): a new question supersedes
  the old turn, whose stream emits `outcome: cancelled` then `done` before
  the new stream opens. Cancellation closes the provider stream — a close,
  not a drain (4.10).

8.8's "note that state was unavailable" has no envelope field and no §4b
event to travel on — the event set is closed — so the note is logged here
at INFO (it carries no question or answer text; 9.11 is untouched) and the
turn proceeds manual-only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any

from dawmans.answer.conversation import Conversation, ConversationStore
from dawmans.answer.envelope import Cause, Outcome, SourceRef, Timings
from dawmans.answer.ground import build_citation, ground_turn
from dawmans.answer.narrow import (
    build_causes,
    build_narrowing,
    expand_entry,
    matched_entry,
)
from dawmans.answer.outcome import (
    Classified,
    Flight,
    GateState,
    in_flight,
    pre_flight,
    required_manual_for,
    resolve_device,
)
from dawmans.answer.parse import MARKER, SUGGESTIONS_MAX, FramingParser
from dawmans.answer.prompt import assemble
from dawmans.answer.provider.base import Provider, ProviderFailure, SynthesisRequest
from dawmans.answer.retrieve import (
    DEFAULT_CONFIG,
    Embedder,
    RetrievalConfig,
    embed_query,
    retrieve,
)

logger = logging.getLogger("dawmans.answer.turn")

FIRST_TOKEN_TIMEOUT_S = 10.0  # 4.9
STATE_TIMEOUT_S = 0.100  # 8.9

_STATE_VALUE_FIELDS = ("key", "value", "observed_at", "origin", "origin_kind")


@dataclass(frozen=True)
class TurnEvent:
    """One named event of the CONTRACTS §4b stream; http/app.py encodes it."""

    name: str
    data: Any


@dataclass(frozen=True)
class ProviderBinding:
    """What a turn reads about the provider, once, at turn start — which is
    what makes a provider change apply to the next turn without restart
    (6.3). `name` names the stalled component on a watchdog timeout (4.9)."""

    provider: Provider | None = None
    kind: str | None = None
    requires_key: bool = False
    credential_stored: bool = False
    requires_ack: bool = False
    acknowledged: bool = False
    name: str = "provider"


class _Handle:
    """One in-flight turn's coordination points (9.13)."""

    def __init__(self) -> None:
        self.supersede = asyncio.Event()
        self.finished = asyncio.Event()
        self.started = False


def _clean_delta(text: str, supplied: dict[str, Any]) -> str:
    # Unresolvable markers are stripped from the streamed text — the user
    # is never shown a dangling reference (3.6). Whitespace is left alone:
    # a caveat continuation's indent is block structure on the consumer side.
    return MARKER.sub(
        lambda match: match.group(0) if match.group(1) in supplied else "", text
    )


@dataclass
class _StreamState:
    outcome_emitted: bool = False
    answer_emitted: bool = False


class TurnPipeline:
    def __init__(
        self,
        watcher: Any,
        binding: Callable[[], ProviderBinding],
        state_source: Any,
        embedder: Embedder,
        count_tokens: Callable[[str], int],
        *,
        conversations: ConversationStore | None = None,
        config: RetrievalConfig = DEFAULT_CONFIG,
        first_token_timeout: float = FIRST_TOKEN_TIMEOUT_S,
        state_timeout: float = STATE_TIMEOUT_S,
    ) -> None:
        self._watcher = watcher
        self._binding = binding
        self._state_source = state_source
        self._embedder = embedder
        self._count_tokens = count_tokens
        self.conversations = conversations if conversations is not None else ConversationStore()
        self._config = config
        self._first_token_timeout = first_token_timeout
        self._state_timeout = state_timeout
        self._inflight: dict[str, _Handle] = {}

    def turn(
        self,
        question: str,
        *,
        sources: Iterable[str] | None = None,
        conversation_id: str | None = None,
    ) -> AsyncIterator[TurnEvent]:
        """Start one turn. The supersede signal is sent synchronously, so
        an in-flight turn on the conversation is cancelled the moment the
        new question arrives, not when the new stream is first read."""
        conversation = self.conversations.get(conversation_id)
        previous = self._inflight.get(conversation.id)
        if previous is not None and not previous.finished.is_set():
            previous.supersede.set()
        handle = _Handle()
        self._inflight[conversation.id] = handle
        return self._run(question, sources, conversation, previous, handle)

    # -- the turn --------------------------------------------------------

    async def _run(
        self,
        question: str,
        sources: Iterable[str] | None,
        conversation: Conversation,
        previous: _Handle | None,
        handle: _Handle,
    ) -> AsyncIterator[TurnEvent]:
        try:
            # 9.13: the old stream finishes — cancelled, then done — before
            # this one opens. An old turn whose generator never ran emits
            # its cancellation whenever it is finally read.
            if previous is not None and previous.started and not previous.finished.is_set():
                await previous.finished.wait()
            handle.started = True
            async for event in self._events(question, sources, conversation, handle):
                yield event
        finally:
            handle.finished.set()
            if self._inflight.get(conversation.id) is handle:
                del self._inflight[conversation.id]

    async def _events(
        self,
        question: str,
        sources: Iterable[str] | None,
        conversation: Conversation,
        handle: _Handle,
    ) -> AsyncIterator[TurnEvent]:
        # The corpus check runs before the turn's timer starts, so a reload
        # is never charged to a turn (§Corpus change detection).
        self._watcher.check()
        view = self._watcher.view
        binding = self._binding()

        unknown: tuple[str, ...] = ()
        if view is not None and sources is not None:
            requested = tuple(sources)
            unknown = tuple(sid for sid in requested if sid not in view.sources_by_id)
            if not unknown:
                conversation.set_scope(requested, view)
        dropped = conversation.prune_scope(view) if view is not None else ()
        if dropped:
            yield TurnEvent("scope_dropped", dropped)

        gated = pre_flight(
            GateState(
                passage_count=len(view.passages) if view is not None else 0,
                unknown_source_ids=unknown,
                selected_count=len(conversation.scope),
                provider_kind=binding.kind,
                requires_key=binding.requires_key,
                credential_stored=binding.credential_stored,
                requires_ack=binding.requires_ack,
                acknowledged=binding.acknowledged,
            )
        )
        if gated is None and binding.provider is None:
            # A kind with no constructed provider is a misconfigured
            # binding; refuse rather than crash mid-turn.
            gated = Classified(Outcome.PROVIDER_UNCONFIGURED, detail="no provider constructed")
        if gated is not None:
            yield TurnEvent("outcome", gated)
            yield TurnEvent("done", {"complete": True})
            return

        started = time.perf_counter()
        scope = conversation.scope
        retrieval_query = conversation.retrieval_query(question)

        def _retrieve():
            t0 = time.perf_counter()
            query = embed_query(self._embedder, retrieval_query)
            result = retrieve(view, retrieval_query, query, scope, config=self._config)
            return result, (time.perf_counter() - t0) * 1000.0

        (retrieval, retrieval_ms), (snapshot, state_ms) = await asyncio.gather(
            asyncio.to_thread(_retrieve), self._acquire_state()
        )
        gather_ms = (time.perf_counter() - started) * 1000.0

        if handle.supersede.is_set():
            yield TurnEvent("outcome", Classified(Outcome.CANCELLED))
            yield TurnEvent("done", {"complete": True})
            return

        supplied_order = [scored.passage_id for scored in retrieval.supplied]
        covered = bool(supplied_order)
        expansion = None
        entry = matched_entry(view, supplied_order)
        if entry is not None:
            expansion = expand_entry(
                view,
                entry["passage_id"],
                scope,
                already_supplied=supplied_order,
                cap=self._config.narrowing_cap,
            )
            if expansion is not None:
                supplied_order.extend(expansion.admitted)
        supplied = {pid: view.passages_by_id[pid] for pid in supplied_order}

        selected = set(scope)
        assembled = assemble(
            question,
            tuple(supplied.values()),
            view.sources_by_id,
            roster=tuple(
                record for record in view.sources if record["source_id"] not in selected
            ),
            history=conversation.history_lines(),
            state=snapshot,
            narrowing_count=conversation.narrowing_count,
            count_tokens=self._count_tokens,
        )
        request = SynthesisRequest(
            system=assembled.system,
            passages=tuple(supplied.values()),
            question=question,
            history=conversation.history_lines(),
            state=snapshot,
            user=assembled.user,
        )

        # -- the provider call, watchdog and cancellation (4.9, 4.10) ----

        body_queue: list[str] = []
        parser = FramingParser(on_body_line=body_queue.append)
        stream_state = _StreamState()
        streamed = False
        first_token_ms: float | None = None
        completion_ms: float | None = None
        provider_ms = 0.0
        failure: ProviderFailure | None = None
        timed_out = False
        cancelled = False

        stream = binding.provider.stream(request)
        issued = time.perf_counter()
        supersede_wait = asyncio.ensure_future(handle.supersede.wait())
        try:
            while True:
                fetch = asyncio.ensure_future(anext(stream))
                done_set, _ = await asyncio.wait(
                    {fetch, supersede_wait},
                    timeout=None if streamed else self._first_token_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if supersede_wait in done_set or not done_set:
                    # Superseded, or the watchdog fired with no first token.
                    cancelled = supersede_wait in done_set
                    timed_out = not cancelled
                    fetch.cancel()
                    await asyncio.gather(fetch, return_exceptions=True)
                    provider_ms = (time.perf_counter() - issued) * 1000.0
                    break
                try:
                    delta = fetch.result()
                except StopAsyncIteration:
                    completion_ms = provider_ms = (time.perf_counter() - issued) * 1000.0
                    break
                except ProviderFailure as fault:
                    failure = fault
                    provider_ms = (time.perf_counter() - issued) * 1000.0
                    break
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - issued) * 1000.0
                streamed = True
                parser.feed(delta)
                for event in self._drain(parser, supplied, body_queue, stream_state):
                    yield event
        finally:
            supersede_wait.cancel()
            try:
                # 4.10: release the provider — a close, not a drain.
                await stream.aclose()
            except Exception as fault:  # noqa: BLE001 - releasing is best-effort on every exit
                logger.debug("provider stream close failed: %s", fault)

        if cancelled:
            yield TurnEvent("outcome", Classified(Outcome.CANCELLED))
            yield TurnEvent("done", {"complete": True})
            return

        if timed_out or failure is not None:
            flight = Flight(
                streamed=streamed,
                failure="timeout" if timed_out else failure.kind,
                retry_after=None if timed_out else failure.retry_after,
                provider=binding.name,
                detail=None if timed_out else failure.detail,
            )
            classified = in_flight(flight)
            yield TurnEvent("outcome", classified)
            yield self._timings(started, gather_ms, retrieval_ms, state_ms,
                                first_token_ms, None, provider_ms)
            yield TurnEvent("done", {"complete": True})
            return

        # -- parse result, grounding, envelope tail (§4b ordering) -------

        parser.close()
        for event in self._drain(parser, supplied, body_queue, stream_state):
            yield event
        result = parser.result(covered=covered, sources=view.sources_by_id)
        ground = ground_turn(result.direct_answer, result.body, supplied, view.sources_by_id)

        if not stream_state.outcome_emitted:
            # The unparsed path — or an empty stream: outcome from the
            # engine's coverage signal, the whole stream as body.
            yield TurnEvent("outcome", Classified(result.outcome))
            if ground.direct_answer:
                yield TurnEvent("direct_answer", ground.direct_answer)
            raw_body = _clean_delta(parser.raw_text, supplied)
            if raw_body.strip():
                yield TurnEvent("body_delta", raw_body)

        narrowing = None
        causes: tuple[Cause, ...] | None = None
        if result.outcome is Outcome.NEEDS_NARROWING:
            narrowing = build_narrowing(expansion) if expansion else result.narrowing
        if result.outcome is Outcome.RANKED_CAUSES:
            if expansion is not None:
                causes = build_causes(expansion)
            else:
                # Fallback ?cause hoists: a model marker that does not
                # resolve is not an addressable value and is dropped.
                causes = tuple(
                    replace(cause, cites=tuple(pid for pid in cause.cites if pid in supplied))
                    for cause in result.causes or ()
                ) or None

        citations = {citation.passage_id: citation for citation in ground.citations}
        if causes:
            # 7.6: every id in cites[]/fix_cites[] resolves into the turn's
            # citations[]; a cause with no fix carries unbacked on its own
            # citation, as a per-turn reading (Decision 10).
            unbacked_ids = {
                pid for cause in causes if not cause.fix_cites for pid in cause.cites
            }
            for cause in causes:
                for pid in (*cause.cites, *cause.fix_cites):
                    if pid in supplied and pid not in citations:
                        citations[pid] = build_citation(
                            supplied[pid], view.sources_by_id[supplied[pid]["source_id"]]
                        )
            for pid in unbacked_ids & set(supplied):
                citations[pid] = build_citation(
                    supplied[pid],
                    view.sources_by_id[supplied[pid]["source_id"]],
                    unbacked_for_turn=True,
                )

        suggested = None
        if result.outcome not in (Outcome.OUT_OF_DOMAIN, Outcome.NO_MANUAL_FOR_DEVICE):
            merged: dict[str, SourceRef] = {}
            if expansion is not None:
                # Decision 10: an out-of-scope fix names its holding source
                # through 2.3's suggestion path.
                for source_id in expansion.suggested_source_ids:
                    record = view.sources_by_id.get(source_id)
                    if record is not None and source_id not in selected:
                        merged[source_id] = SourceRef(
                            source_id=source_id, display_name=record["display_name"]
                        )
            for ref in result.suggested_sources or ():
                merged.setdefault(ref.source_id, ref)
            suggested = tuple(list(merged.values())[:SUGGESTIONS_MAX]) or None

        device = manual = None
        if result.outcome is Outcome.NO_MANUAL_FOR_DEVICE and result.required_device:
            device = resolve_device(result.required_device, view.gaps)
            manual = required_manual_for(device, view.gaps)

        for citation in citations.values():
            yield TurnEvent("citation", citation)
        for cause in causes or ():
            yield TurnEvent("cause", cause)
        yield TurnEvent(
            "contributing_sources",
            tuple(sorted({record["source_id"] for record in supplied.values()})),
        )
        if result.uncovered_parts:
            yield TurnEvent("uncovered_parts", result.uncovered_parts)
        if suggested:
            yield TurnEvent("suggested_sources", suggested)
        if narrowing is not None:
            yield TurnEvent("narrowing", narrowing)
        if device is not None:
            yield TurnEvent("required_device", device)
            if manual is not None:
                yield TurnEvent("required_manual", manual)
        if ground.ungrounded:
            yield TurnEvent("ungrounded", True)
        yield TurnEvent("framing", result.framing)
        yield self._timings(started, gather_ms, retrieval_ms, state_ms,
                            first_token_ms, completion_ms, provider_ms)
        conversation.record_turn(question, result.outcome, ground.direct_answer or "")
        yield TurnEvent("done", {"complete": True})

    # -- helpers ---------------------------------------------------------

    async def _acquire_state(self):
        """8.8/8.9: bounded, and a failure, timeout or malformed snapshot
        degrades the turn to manual-only — with the note logged — and
        never fails it."""
        t0 = time.perf_counter()
        try:
            snapshot = await asyncio.wait_for(
                self._state_source.snapshot(), self._state_timeout
            )
            for value in tuple(snapshot.values):
                for field in _STATE_VALUE_FIELDS:
                    getattr(value, field)
        except Exception as fault:  # noqa: BLE001 - any state fault degrades, never fails (8.8)
            logger.info("session state unavailable (%s); answering manual-only", fault)
            return None, (time.perf_counter() - t0) * 1000.0
        return snapshot, (time.perf_counter() - t0) * 1000.0

    def _drain(
        self,
        parser: FramingParser,
        supplied: dict[str, Any],
        body_queue: list[str],
        stream_state: _StreamState,
    ) -> list[TurnEvent]:
        """Events the accumulated parse can already justify, in §4b order:
        outcome from line 1, direct_answer from line 2, then body deltas.
        The unparsed path emits nothing here — its events are derived at
        close, which is the honest degradation for a provider that ignored
        the framing."""
        if parser.line_one is None or not parser.hoisting:
            return []
        events: list[TurnEvent] = []
        if not stream_state.outcome_emitted:
            events.append(TurnEvent("outcome", Classified(Outcome(parser.line_one))))
            stream_state.outcome_emitted = True
        if not stream_state.answer_emitted and parser.line_count >= 2:
            events.append(
                TurnEvent(
                    "direct_answer",
                    _clean_delta(parser.direct_answer_line or "", supplied),
                )
            )
            stream_state.answer_emitted = True
        if stream_state.answer_emitted:
            while body_queue:
                line = body_queue.pop(0)
                events.append(TurnEvent("body_delta", _clean_delta(line, supplied) + "\n"))
        return events

    def _timings(
        self,
        started: float,
        gather_ms: float,
        retrieval_ms: float,
        state_ms: float,
        first_token_ms: float | None,
        completion_ms: float | None,
        provider_ms: float,
    ) -> TurnEvent:
        total_ms = (time.perf_counter() - started) * 1000.0
        return TurnEvent(
            "timings",
            Timings(
                retrieval_ms=retrieval_ms,
                state_acquisition_ms=state_ms,
                engine_overhead_ms=max(0.0, total_ms - gather_ms - provider_ms),
                first_token_ms=first_token_ms,
                completion_ms=completion_ms,
                corpus_reload_ms=self._watcher.corpus_reload_ms,
            ),
        )
