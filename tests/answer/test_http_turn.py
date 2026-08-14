"""The turn stream over POST /turn (1.8, 4.5, 9.10, 9.12, 9.14, 9.15).

SSE over the POST response — EventSource cannot POST. The event set is
CONTRACTS §4b's sixteen, in its ordering, and `done` carries a payload:
a payload-free terminator is never dispatched by a conforming reader, so
a completed turn would be indistinguishable from a truncated one.

The incremental and disconnect tests drive the raw ASGI app so the
messages are observed as they are sent — a buffered client would only
show the finished stream.
"""

import asyncio
import json
import logging

import numpy as np
from corpus_fixtures import make_view
from http_fixtures import (
    APC,
    LIVE,
    PASSAGES,
    PORT,
    SOURCES,
    TRIAGE,
    StubWatcher,
    default_view,
    get,
    make_app,
    parse_sse,
    request,
)

from dawmans.answer.envelope import Outcome
from dawmans.answer.provider.base import ProbeResult, ProviderKind, ProviderStatus
from dawmans.answer.state.null import NullStateSource
from dawmans.answer.turn import ProviderBinding, TurnPipeline

ALL = (LIVE, APC, TRIAGE)
Q_BOTH = np.array([0.8, 0.0, 0.9, 0.0], dtype=np.float32)
Q_TRIAGE = np.array([0.5, 0.0, 0.0, 0.9], dtype=np.float32)

# CONTRACTS §4b: the closed event set.
EVENT_SET = {
    "scope_dropped",
    "outcome",
    "direct_answer",
    "body_delta",
    "citation",
    "cause",
    "contributing_sources",
    "uncovered_parts",
    "suggested_sources",
    "narrowing",
    "required_device",
    "required_manual",
    "ungrounded",
    "framing",
    "timings",
    "done",
}

# The uncited ordered step is fact-shaped and uncited — the ungrounded
# arm — and the ~uncovered sigil hoists into uncovered_parts.
ANSWERED_SCRIPT = (
    "answered\n",
    f"Turn the Track Activator back on. [[p:{LIVE}#p1]]\n",
    "---\n",
    "## Why\n",
    f"The Track Activator mutes the track output. [[p:{LIVE}#p1]]\n",
    "\n",
    "1. Press the Session View button now\n",
    "~uncovered whether direct monitoring is also muted\n",
)

RANKED_SCRIPT = (
    "ranked-causes\n",
    "Look for a dimmed track number in the mixer.\n",
    "---\n",
    f"Two candidates remain. [[p:{TRIAGE}#t1]]\n",
)


class ScriptedProvider:
    kind = ProviderKind.LOCAL

    def __init__(self, script=ANSWERED_SCRIPT, *, gate_after=None):
        self.script = script
        self.gate_after = gate_after
        self.gate = asyncio.Event()
        self.requests = []
        self.closed = False

    def status(self):
        return ProviderStatus(kind=self.kind, configured=True)

    async def probe(self):
        return ProbeResult(reachable=True)

    async def stream(self, req):
        self.requests.append(req)
        try:
            for position, delta in enumerate(self.script):
                if position == self.gate_after:
                    await self.gate.wait()
                yield delta
        finally:
            self.closed = True


class StubEmbedder:
    def __init__(self, vector):
        self.vector = vector

    def embed(self, texts):
        return [np.asarray(self.vector, dtype=np.float32)]


def make_pipeline(provider, *, view=None, query=Q_BOTH):
    watcher = StubWatcher(view if view is not None else default_view())
    pipeline = TurnPipeline(
        watcher=watcher,
        binding=lambda: ProviderBinding(
            provider=provider, kind=str(provider.kind), name="stub-local"
        ),
        state_source=NullStateSource(),
        embedder=StubEmbedder(query),
        count_tokens=lambda text: len(text.split()),
    )
    return pipeline, watcher


def turn_app(provider=None, *, query=Q_BOTH):
    provider = provider or ScriptedProvider()
    pipeline, watcher = make_pipeline(provider, query=query)
    app = make_app(watcher, pipeline=pipeline)
    return app, pipeline, provider


def post_turn(app, body):
    return request(app, "POST", "/turn", json_body=body)


def stream_turn(app, body):
    response = post_turn(app, body)
    assert response.status_code == 200
    return response, parse_sse(response.text)


# -- the raw ASGI driver for incremental observation ---------------------


def turn_scope():
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/turn",
        "raw_path": b"/turn",
        "query_string": b"",
        "root_path": "",
        "server": ("127.0.0.1", PORT),
        "client": ("127.0.0.1", 40000),
        "headers": [
            (b"host", f"127.0.0.1:{PORT}".encode()),
            (b"content-type", b"application/json"),
        ],
    }


def drive(app, body, sent, disconnect):
    delivered = asyncio.Event()

    async def receive():
        if not delivered.is_set():
            delivered.set()
            return {
                "type": "http.request",
                "body": json.dumps(body).encode(),
                "more_body": False,
            }
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    return app(turn_scope(), receive, send)


def sent_bytes(sent):
    return b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )


async def until(condition, timeout_s=5.0):
    for _ in range(int(timeout_s / 0.005)):
        if condition():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition never became true")


class TestStreamShape:
    def test_sse_over_the_post_response(self):
        app, _, _ = turn_app()
        response = post_turn(app, {"question": "why is track 3 silent", "sources": list(ALL)})
        assert response.headers["content-type"].startswith("text/event-stream")

    def test_the_version_token_is_a_response_header(self):
        app, _, _ = turn_app()
        response = post_turn(app, {"question": "why", "sources": list(ALL)})
        assert response.headers["dawmans-turn-stream"] == "dawmans/turn-stream/1"

    def test_stream_completeness_every_pipeline_event_reaches_the_wire(self):
        # The engine-side truth is the pipeline's own event sequence; the
        # wire must carry exactly that, name for name, nothing else.
        direct_pipeline, _ = make_pipeline(ScriptedProvider())

        async def collect():
            return [
                event.name
                async for event in direct_pipeline.turn(
                    "why is track 3 silent", sources=ALL
                )
            ]

        direct_names = asyncio.run(collect())

        app, _, _ = turn_app()
        _, events = stream_turn(app, {"question": "why is track 3 silent", "sources": list(ALL)})
        assert [name for name, _ in events] == direct_names
        assert set(direct_names) <= EVENT_SET

    def test_no_event_outside_the_sixteen_and_done_exactly_once_with_payload(self):
        app, _, _ = turn_app()
        _, events = stream_turn(app, {"question": "why is track 3 silent", "sources": list(ALL)})
        names = [name for name, _ in events]
        assert set(names) <= EVENT_SET
        assert names.count("done") == 1
        assert names[-1] == "done"
        assert events[-1][1] == {"complete": True}

    def test_each_event_carries_its_named_field(self):
        app, _, _ = turn_app()
        _, events = stream_turn(app, {"question": "why is track 3 silent", "sources": list(ALL)})
        payloads = {}
        for name, data in events:
            payloads.setdefault(name, data)
        assert payloads["outcome"]["outcome"] == "answered"
        assert "Track Activator" in payloads["direct_answer"]["text"]
        assert "text" in payloads["body_delta"]
        citation = payloads["citation"]
        assert citation["passage_id"] == f"{LIVE}#p1"
        assert citation["kind"] == "vendor-manual"
        # Absent is absent, not null (CONTRACTS §3).
        assert "section_number" not in citation
        # The lexical arm supplies the triage entry too ("track" overlaps),
        # so all three sources contribute.
        assert payloads["contributing_sources"]["sources"] == sorted({LIVE, APC, TRIAGE})
        assert payloads["uncovered_parts"]["parts"] == [
            "whether direct monitoring is also muted"
        ]
        assert payloads["ungrounded"] == {"ungrounded": True}
        assert payloads["framing"] == {"framing": "parsed"}
        assert payloads["timings"]["retrieval_ms"] is not None
        assert "completion_ms" in payloads["timings"]


class TestOrdering:
    def test_outcome_precedes_every_other_event_and_direct_answer_precedes_body(self):
        app, _, _ = turn_app()
        _, events = stream_turn(app, {"question": "why is track 3 silent", "sources": list(ALL)})
        names = [name for name, _ in events]
        assert names[0] == "outcome"
        assert names.index("direct_answer") < names.index("body_delta")
        # 1.8 on the wire: the answer-first shape is stream order, not
        # a rendering courtesy.
        last_delta = len(names) - 1 - names[::-1].index("body_delta")
        assert names.index("ungrounded") > last_delta
        assert names[-1] == "done"

    def test_cause_events_arrive_in_rank_order(self):
        provider = ScriptedProvider(RANKED_SCRIPT)
        pipeline, watcher = make_pipeline(provider, query=Q_TRIAGE)
        app = make_app(watcher, pipeline=pipeline)
        conversation = pipeline.conversations.get(None)
        conversation.set_scope(ALL, watcher.view)
        conversation.record_turn("no sound", Outcome.NEEDS_NARROWING, "Which?")
        conversation.record_turn("neither", Outcome.NEEDS_NARROWING, "Then which?")
        _, events = stream_turn(
            app, {"question": "still neither", "conversation_id": conversation.id}
        )
        ranks = [data["rank"] for name, data in events if name == "cause"]
        assert ranks == [1, 2]
        names = [name for name, _ in events]
        assert names.index("outcome") < names.index("cause")

    def test_scope_dropped_precedes_outcome(self):
        app, pipeline, _ = turn_app()
        conversation = pipeline.conversations.get(None)
        stream_turn(
            app,
            {
                "question": "why is track 3 silent",
                "sources": list(ALL),
                "conversation_id": conversation.id,
            },
        )
        watcher = pipeline._watcher
        shrunk = make_view(
            [SOURCES[0]], PASSAGES[:2], vectors=np.eye(4, dtype=np.float32)[:2]
        )
        watcher.swap(shrunk)
        _, events = stream_turn(
            app, {"question": "and now?", "conversation_id": conversation.id}
        )
        names = [name for name, _ in events]
        assert "scope_dropped" in names
        assert names.index("scope_dropped") < names.index("outcome")
        dropped = next(data for name, data in events if name == "scope_dropped")
        assert {member["source_id"] for member in dropped} == {APC, TRIAGE}


class TestIncrementalDelivery:
    def test_the_version_header_is_readable_before_the_first_body_byte(self):
        async def scenario():
            app, _, _ = turn_app()
            sent = []
            await drive(app, {"question": "why", "sources": list(ALL)}, sent, asyncio.Event())
            return sent

        sent = asyncio.run(scenario())
        start = sent[0]
        assert start["type"] == "http.response.start"
        headers = dict(start["headers"])
        assert headers[b"dawmans-turn-stream"] == b"dawmans/turn-stream/1"

    def test_body_deltas_arrive_while_the_provider_is_still_streaming(self):
        async def scenario():
            provider = ScriptedProvider(gate_after=6)
            pipeline, watcher = make_pipeline(provider)
            app = make_app(watcher, pipeline=pipeline)
            sent = []
            task = asyncio.create_task(
                drive(app, {"question": "why", "sources": list(ALL)}, sent, asyncio.Event())
            )
            await until(lambda: b"event: body_delta" in sent_bytes(sent))
            # The provider is gated mid-script: what has arrived arrived
            # before synthesis completed, and done is not yet on the wire.
            withheld = b"event: done" not in sent_bytes(sent) and not provider.closed
            provider.gate.set()
            await task
            return withheld, sent_bytes(sent)

        withheld, wire = asyncio.run(scenario())
        assert withheld
        assert b"event: done" in wire

    def test_a_caller_disconnect_mid_stream_is_cancellation(self):
        async def scenario():
            provider = ScriptedProvider(gate_after=6)
            pipeline, watcher = make_pipeline(provider)
            app = make_app(watcher, pipeline=pipeline)
            sent = []
            disconnect = asyncio.Event()
            task = asyncio.create_task(
                drive(app, {"question": "why", "sources": list(ALL)}, sent, disconnect)
            )
            await until(lambda: b"event: body_delta" in sent_bytes(sent))
            disconnect.set()
            await task
            # 9.10/4.10: the provider stream is released — a close, not a
            # drain — and the turn never claims completion.
            await until(lambda: provider.closed)
            return sent_bytes(sent)

        wire = asyncio.run(scenario())
        assert b"event: done" not in wire


class TestQuestionLimit:
    def test_a_1001_character_question_is_rejected_before_a_turn_exists(self):
        app, _, provider = turn_app()
        response = post_turn(
            app, {"question": "a" * 1001, "sources": list(ALL)}
        )
        assert response.status_code == 422
        body = response.json()
        assert body == {
            "rejected": "question-too-long",
            "limit": 1000,
            "received": 1001,
        }
        # No outcome, no envelope, no truncation: no turn was started and
        # the §6 taxonomy does not describe it (9.12).
        assert "outcome" not in body
        assert provider.requests == []

    def test_a_1000_character_question_is_accepted(self):
        app, _, _ = turn_app()
        response = post_turn(app, {"question": "a" * 1000, "sources": list(ALL)})
        assert response.status_code == 200

    def test_a_missing_question_is_422_without_an_outcome(self):
        app, _, _ = turn_app()
        response = post_turn(app, {"sources": list(ALL)})
        assert response.status_code == 422
        assert "outcome" not in response.json()


class TestConversationHeader:
    def test_the_minted_conversation_id_is_readable_before_the_body(self):
        app, _, _ = turn_app()
        response = post_turn(app, {"question": "why", "sources": list(ALL)})
        minted = response.headers["dawmans-conversation-id"]
        assert minted
        # A follow-up on the returned id continues the same conversation.
        response = post_turn(app, {"question": "and?", "conversation_id": minted})
        assert response.headers["dawmans-conversation-id"] == minted


class TestLogging:
    def test_question_text_does_not_log_at_default_level(self, caplog):
        question = "why is track 3 silent"
        app, _, _ = turn_app()
        with caplog.at_level(logging.INFO):
            stream_turn(app, {"question": question, "sources": list(ALL)})
        for record in caplog.records:
            assert question not in record.getMessage()


class TestStaticMount:
    def test_the_built_surface_is_served_at_root_same_origin(self, tmp_path):
        build = tmp_path / "build"
        build.mkdir()
        (build / "index.html").write_text("<html>dawmans surface</html>")
        (build / "app.js").write_text("console.log('dawmans')")
        app = make_app(StubWatcher(default_view()), static_dir=build)
        response = get(app, "/")
        assert response.status_code == 200
        assert "dawmans surface" in response.text
        assert get(app, "/app.js").status_code == 200

    def test_the_mount_does_not_shadow_the_api_routes(self, tmp_path):
        build = tmp_path / "build"
        build.mkdir()
        (build / "index.html").write_text("<html>surface</html>")
        app = make_app(StubWatcher(default_view()), static_dir=build)
        assert get(app, "/sources").status_code == 200
