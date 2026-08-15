"""End-to-end turns over a synthetic on-disk view and scripted providers.

The whole served stack is in the loop: a real `ViewWatcher` over an index
tree written to disk (view directory first, manifest last, as the corpus
commits it), the guarded Starlette app, the turn pipeline, and a scripted
provider standing in for the one network hop. One turn per content
outcome, the narrowing entry path run to its limit, and the
mid-conversation corpus swap of 5.10/5.11.

Vectors on disk are one-hot rows, so the stub embedder's query vector
states every cosine directly — the same trick as `corpus_fixtures`, but
through the real load path.

The startup order and the serve wiring are `test_serve.py`'s — those tests
exercise `dawmans.cli.run_serve`, which the turns here deliberately bypass
so a scripted provider and a stub embedder can drive retrieval exactly.
"""

import json
import os

import bm25s
import numpy as np
from corpus_fixtures import passage, sidecar_entry, triage_source, vendor_source
from http_fixtures import PORT, parse_sse, request

from dawmans.answer.http.app import create_app
from dawmans.answer.provider.base import ProbeResult, ProviderKind, ProviderStatus
from dawmans.answer.state.null import NullStateSource
from dawmans.answer.turn import ProviderBinding, TurnPipeline
from dawmans.answer.view import ViewWatcher

LIVE = "ableton/live-12"
APC = "akai/apc-key-25"
TRIAGE = "authored/triage"
ALL = (LIVE, APC, TRIAGE)

SOURCES = [
    vendor_source(LIVE, LIVE, page_count=1009),
    vendor_source(APC, APC, page_count=5, status="assumed"),
    triage_source(),
]

# Row order: LIVE#p1, LIVE#p2, APC#p1, TRIAGE#t1 — one-hot dimensions 0-3.
PASSAGES = [
    passage(f"{LIVE}#p1", "The Track Activator mutes the track output", section_number="16.4"),
    passage(f"{LIVE}#p2", "Click the dimmed track number to re-enable the track"),
    passage(f"{APC}#p1", "Hold SHIFT and press a pad to select a scene"),
    passage(
        f"{TRIAGE}#t1",
        "No sound from a track although the meters move",
        entry_location="triage/no-sound-from-track.md:7",
    ),
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

# The fixture gaps report: owned-but-undocumented is the sole resolver of a
# canonical device id, empty against the live corpus, so the dormant
# no-manual-for-device path is only testable against this.
GAPS = {
    "owned_but_undocumented": [{"device": "roland/tr-8s", "display_name": "Roland TR-8S"}],
    "documented_but_unconfirmed": [{"source_id": APC, "status": "assumed"}],
}

VECTOR_DIM = 4

# One-hot query components per row: LIVE#p1, LIVE#p2, APC#p1, TRIAGE#t1.
Q_ALL = np.array([0.9, 0.0, 0.5, 0.8], dtype=np.float32)
Q_CONFLICT = np.array([0.9, 0.0, 0.8, 0.4], dtype=np.float32)
Q_TRIAGE = np.array([0.5, 0.0, 0.0, 0.9], dtype=np.float32)
Q_TRIAGE_ONLY = np.array([0.0, 0.0, 0.0, 0.9], dtype=np.float32)
Q_LIVE = np.array([0.9, 0.0, 0.0, 0.0], dtype=np.float32)


def write_index(root, sources, passages, *, vectors, gaps=GAPS, sidecar=(), view="views/r1", revision="rev-1"):
    """Write one complete index revision the way the corpus commits it:
    the view directory in full first, the manifest rename last."""
    index_dir = root / "index"
    view_dir = index_dir / view
    (view_dir / "reports").mkdir(parents=True, exist_ok=True)

    (view_dir / "sources.json").write_text(json.dumps(list(sources)))
    (view_dir / "passages.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in passages)
    )
    np.save(view_dir / "vectors.npy", np.asarray(vectors, dtype=np.float32))
    tokens = bm25s.tokenize(
        [record["text"] for record in passages], stopwords=None, show_progress=False
    )
    lexical = bm25s.BM25()
    lexical.index(tokens, show_progress=False)
    lexical.save(str(view_dir / "lexical"))
    (view_dir / "gaps.json").write_text(json.dumps(gaps))
    if any(record["kind"] == "authored-triage" for record in sources):
        (view_dir / "reports" / "authored_triage.json").write_text(
            json.dumps({"passages": list(sidecar), "report": {"entries": len(list(sidecar))}})
        )

    manifest_sources = []
    row_start = 0
    for record in sources:
        count = sum(1 for p in passages if p["source_id"] == record["source_id"])
        manifest_sources.append(
            {"source_id": record["source_id"], "row_start": row_start, "row_count": count}
        )
        row_start += count
    manifest_path = index_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "index_version": 1,
                "view_dir": view,
                "corpus_revision": revision,
                "sources": manifest_sources,
            }
        )
    )
    # Force a distinct stat so the swap never rides on timestamp granularity.
    stat = os.stat(manifest_path)
    os.utime(manifest_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    return index_dir


def default_index(root):
    return write_index(
        root, SOURCES, PASSAGES, vectors=np.eye(VECTOR_DIM, dtype=np.float32), sidecar=[ENTRY]
    )


class ScriptedProvider:
    kind = ProviderKind.LOCAL

    def __init__(self, script):
        self.script = tuple(script)
        self.requests = []

    def status(self):
        return ProviderStatus(kind=self.kind, configured=True)

    async def probe(self):
        return ProbeResult(reachable=True)

    async def stream(self, req):
        self.requests.append(req)
        for delta in self.script:
            yield delta


class SettableEmbedder:
    """The stub query encoder: whatever vector the test set last."""

    def __init__(self, vector=Q_ALL):
        self.vector = vector

    def embed(self, texts):
        return [np.asarray(self.vector, dtype=np.float32)]


class Stack:
    """The full served stack over a disk index, minus the socket."""

    def __init__(self, tmp_path, index_dir=None):
        self.index_dir = index_dir if index_dir is not None else default_index(tmp_path)
        self.watcher = ViewWatcher(self.index_dir)
        self.embedder = SettableEmbedder()
        self.provider = None
        self.pipeline = TurnPipeline(
            watcher=self.watcher,
            binding=lambda: ProviderBinding(
                provider=self.provider, kind=str(ProviderKind.LOCAL), name="scripted-local"
            ),
            state_source=NullStateSource(),
            embedder=self.embedder,
            count_tokens=lambda text: len(text.split()),
        )
        self.app = create_app(watcher=self.watcher, port=PORT, pipeline=self.pipeline)

    def turn(self, question, *, script, query, sources=None, conversation_id=None):
        self.provider = ScriptedProvider(script)
        self.embedder.vector = query
        body = {"question": question}
        if sources is not None:
            body["sources"] = list(sources)
        if conversation_id is not None:
            body["conversation_id"] = conversation_id
        response = request(self.app, "POST", "/turn", json_body=body)
        assert response.status_code == 200
        return response.headers["dawmans-conversation-id"], parse_sse(response.text)


def payloads(events):
    held = {}
    for name, data in events:
        held.setdefault(name, []).append(data)
    return held


def outcome_of(events):
    return next(data["outcome"] for name, data in events if name == "outcome")


def body_text(events):
    return "".join(data["text"] for name, data in events if name == "body_delta")


class TestContentOutcomes:
    def test_answered_with_citations_from_both_kinds(self, tmp_path):
        stack = Stack(tmp_path)
        _, events = stack.turn(
            "why is track 3 silent",
            script=(
                "answered\n",
                f"Turn the Track Activator back on. [[p:{LIVE}#p1]]\n",
                "---\n",
                f"The Track Activator mutes the track output. [[p:{LIVE}#p1]]\n",
                f"The triage entry names it as the cause of silence. [[p:{TRIAGE}#t1]]\n",
            ),
            query=Q_ALL,
            sources=ALL,
        )
        assert outcome_of(events) == "answered"
        citations = {c["passage_id"]: c for c in [d for n, d in events if n == "citation"]}
        vendor = citations[f"{LIVE}#p1"]
        assert vendor["kind"] == "vendor-manual"
        assert vendor["doc_version"] == "1.0"
        assert vendor["hardware_applicability"] == "confirmed"
        authored = citations[f"{TRIAGE}#t1"]
        assert authored["kind"] == "authored-triage"
        assert authored["hardware_applicability"] == "assumed"
        assert authored["entry_location"] == "triage/no-sound-from-track.md:7"
        # Authored citations are pageless: absent, never synthesised.
        assert "doc_version" not in authored
        assert "page" not in authored

    def test_contributing_sources_is_the_set_over_supplied_on_every_answer(self, tmp_path):
        stack = Stack(tmp_path)
        _, events = stack.turn(
            "why is track 3 silent",
            script=("answered\n", "Check the track.\n", "---\n", "Nothing else.\n"),
            query=Q_ALL,
            sources=ALL,
        )
        [contributing] = [d for n, d in events if n == "contributing_sources"]
        # Supplied-derived, never citation-derived: the script cited
        # nothing, yet every source that supplied a passage is named.
        assert not [d for n, d in events if n == "citation"]
        assert contributing["sources"] == sorted(ALL)

    def test_a_conflict_renders_both_readings_with_separate_citations(self, tmp_path):
        stack = Stack(tmp_path)
        _, events = stack.turn(
            "does the controller or the manual govern monitoring",
            script=(
                "answered\n",
                f"The sources disagree on monitor routing. [[p:{LIVE}#p1]]\n",
                "---\n",
                "!conflict monitor routing\n",
                f"- The manual says the Track Activator mutes the output. [[p:{LIVE}#p1]]\n",
                f"- The guide says SHIFT plus a pad selects the scene. [[p:{APC}#p1]]\n",
            ),
            query=Q_CONFLICT,
            sources=ALL,
        )
        body = body_text(events)
        # The conflict block rides in body with both readings unchosen,
        # each keeping its own inline citation marker.
        assert "!conflict monitor routing" in body
        assert f"- The manual says the Track Activator mutes the output. [[p:{LIVE}#p1]]" in body
        assert f"[[p:{APC}#p1]]" in body
        cited = {c["passage_id"]: c for c in [d for n, d in events if n == "citation"]}
        assert cited[f"{LIVE}#p1"]["source_id"] == LIVE
        assert cited[f"{APC}#p1"]["source_id"] == APC

    def test_a_partial_answer_names_its_uncovered_parts(self, tmp_path):
        stack = Stack(tmp_path)
        _, events = stack.turn(
            "is direct monitoring also muted",
            script=(
                "partially-answered\n",
                f"The track output is muted by the Track Activator. [[p:{LIVE}#p1]]\n",
                "---\n",
                f"That is what the manual states. [[p:{LIVE}#p1]]\n",
                "~uncovered whether the interface's direct monitoring is also muted\n",
            ),
            query=Q_ALL,
            sources=ALL,
        )
        assert outcome_of(events) == "partially-answered"
        [parts] = [d for n, d in events if n == "uncovered_parts"]
        assert parts["parts"] == ["whether the interface's direct monitoring is also muted"]

    def test_a_refusal_carries_up_to_three_resolved_suggestions(self, tmp_path):
        stack = Stack(tmp_path)
        _, events = stack.turn(
            "how do I re-enable a muted track",
            script=(
                "refused-not-covered\n",
                "The selected source does not state this.\n",
                "---\n",
                "Nothing in the triage entries covers the control itself.\n",
                f"!suggest {LIVE}\n",
                f"!suggest {APC}\n",
                "!suggest vendor/never-ingested\n",
            ),
            query=Q_TRIAGE_ONLY,
            sources=(TRIAGE,),
        )
        assert outcome_of(events) == "refused-not-covered"
        [suggested] = [d for n, d in events if n == "suggested_sources"]
        # A model-invented id is not an addressable value: dropped, and the
        # survivors carry display names resolved against sources.json.
        assert [ref["source_id"] for ref in suggested] == [LIVE, APC]
        assert all(ref["display_name"] for ref in suggested)
        assert len(suggested) <= 3

    def test_out_of_domain_suppresses_suggestions(self, tmp_path):
        stack = Stack(tmp_path)
        _, events = stack.turn(
            "how do I make my kick knock",
            script=(
                "out-of-domain\n",
                "No manual documents production technique.\n",
                "---\n",
                "A reference manual documents controls, not practice.\n",
                f"!suggest {LIVE}\n",
            ),
            query=Q_TRIAGE_ONLY,
            sources=(TRIAGE,),
        )
        assert outcome_of(events) == "out-of-domain"
        assert not [d for n, d in events if n == "suggested_sources"]

    def test_no_manual_for_device_resolves_through_the_fixture_gaps_report(self, tmp_path):
        stack = Stack(tmp_path)
        _, events = stack.turn(
            "how do I set swing on the TR-8S",
            script=(
                "no-manual-for-device\n",
                "No ingested manual covers the TR-8S.\n",
                "---\n",
                "@device Roland TR-8S\n",
            ),
            query=Q_ALL,
            sources=ALL,
        )
        assert outcome_of(events) == "no-manual-for-device"
        [device] = [d for n, d in events if n == "required_device"]
        # The @device name matched owned-but-undocumented: the canonical id
        # and the rig display name substitute for the model's wording.
        assert device == {"device": "roland/tr-8s", "display_name": "Roland TR-8S"}
        [manual] = [d for n, d in events if n == "required_manual"]
        assert manual["filename"] == "roland_tr-8s_<doctype>_v<version>_<lang>.pdf"
        assert manual["placeholders"] == ["doctype", "version", "lang"]


NARROWING_SCRIPT = (
    "needs-narrowing\n",
    "Which of these do you see?\n",
    "---\n",
    f"Two documented causes match the symptom. [[p:{TRIAGE}#t1]]\n",
)

RANKED_SCRIPT = (
    "ranked-causes\n",
    "Look at the mixer for a dimmed track number.\n",
    "---\n",
    f"Two candidates remain, most likely first. [[p:{TRIAGE}#t1]]\n",
)


class TestNarrowingRunToTheLimit:
    def test_the_entry_path_terminates_in_ranked_causes(self, tmp_path):
        stack = Stack(tmp_path)

        conversation_id, events = stack.turn(
            "no sound from track 3",
            script=NARROWING_SCRIPT,
            query=Q_TRIAGE,
            sources=ALL,
        )
        assert outcome_of(events) == "needs-narrowing"
        [narrowing] = [d for n, d in events if n == "narrowing"]
        # Engine-built from the sidecar entry, in the entry's own order:
        # label from check, value from statement, no reorder, no addition.
        assert [c["label"] for c in narrowing["candidates"]] == [
            "the track number is dimmed in the mixer",
            "no pad is lit on the controller",
        ]
        assert [c["value"] for c in narrowing["candidates"]] == [
            "The Track Activator is off",
            "The scene is not launched",
        ]

        _, events = stack.turn(
            "neither of those",
            script=NARROWING_SCRIPT,
            query=Q_TRIAGE,
            conversation_id=conversation_id,
        )
        assert outcome_of(events) == "needs-narrowing"

        _, events = stack.turn(
            "still neither",
            script=RANKED_SCRIPT,
            query=Q_TRIAGE,
            conversation_id=conversation_id,
        )
        assert outcome_of(events) == "ranked-causes"
        # 7.5's mechanism: at the limit the assembled prompt forbids
        # ?narrow and directs the terminal form.
        prompt = stack.provider.requests[-1].user
        assert "Narrowing limit reached" in prompt
        assert "Do not emit ?narrow" in prompt

        causes = [d for n, d in events if n == "cause"]
        assert [c["rank"] for c in causes] == [1, 2]
        assert causes[0]["statement"] == "The Track Activator is off"
        assert causes[0]["check"] == "the track number is dimmed in the mixer"
        assert causes[0]["cites"] == [f"{TRIAGE}#t1"]
        assert causes[0]["fix_cites"] == [f"{LIVE}#p2"]
        assert causes[1]["fix_cites"] == [f"{APC}#p1"]

        # direct_answer states the rank-1 check as an instruction, never
        # the cause itself — engine-built on the entry path, replacing the
        # model's line 2.
        [direct] = [d for n, d in events if n == "direct_answer"]
        assert direct["text"] == "Check whether the track number is dimmed in the mixer."
        assert "Track Activator is off" not in direct["text"]

        # Every cites[]/fix_cites[] id resolves into the turn's citations.
        cited = {c["passage_id"] for c in [d for n, d in events if n == "citation"]}
        for cause in causes:
            assert set(cause["cites"]) <= cited
            assert set(cause["fix_cites"]) <= cited


class TestCorpusSwapMidConversation:
    def test_a_removed_source_drops_and_the_last_removal_empties_the_scope(self, tmp_path):
        stack = Stack(tmp_path)
        conversation_id, events = stack.turn(
            "why is track 3 silent",
            script=("answered\n", f"Turn it back on. [[p:{LIVE}#p1]]\n", "---\n", "Done.\n"),
            query=Q_ALL,
            sources=ALL,
        )
        assert outcome_of(events) == "answered"

        # Re-ingest: APC and the triage source leave the corpus. The next
        # turn discards the old view before it retrieves.
        write_index(
            tmp_path,
            [SOURCES[0]],
            PASSAGES[:2],
            vectors=np.eye(VECTOR_DIM, dtype=np.float32)[:2],
            view="views/r2",
            revision="rev-2",
        )
        _, events = stack.turn(
            "and is the fader down?",
            script=("answered\n", f"No, the activator. [[p:{LIVE}#p1]]\n", "---\n", "See above.\n"),
            query=Q_LIVE,
            conversation_id=conversation_id,
        )
        assert stack.watcher.view.corpus_revision == "rev-2"
        names = [n for n, _ in events]
        assert names.index("scope_dropped") < names.index("outcome")
        [dropped] = [d for n, d in events if n == "scope_dropped"]
        assert {ref["source_id"] for ref in dropped} == {APC, TRIAGE}
        # The turn ran against the new revision: only the surviving source
        # supplied passages.
        [contributing] = [d for n, d in events if n == "contributing_sources"]
        assert contributing["sources"] == [LIVE]

        # A third revision without the last carried source: the scope is
        # emptied, reported, and the turn is no-sources-selected — the
        # corpus is not empty, so nothing lies about that.
        write_index(
            tmp_path,
            [vendor_source("other/thing", "other/thing")],
            [passage("other/thing#p1", "Something entirely different")],
            vectors=np.eye(VECTOR_DIM, dtype=np.float32)[:1],
            view="views/r3",
            revision="rev-3",
        )
        _, events = stack.turn(
            "so what now?",
            script=("answered\n", "Never reached.\n", "---\n", "Never.\n"),
            query=Q_LIVE,
            conversation_id=conversation_id,
        )
        names = [n for n, _ in events]
        assert names.index("scope_dropped") < names.index("outcome")
        [dropped] = [d for n, d in events if n == "scope_dropped"]
        assert {ref["source_id"] for ref in dropped} == {LIVE}
        assert outcome_of(events) == "no-sources-selected"
        # The provider was never called: no turn content exists.
        assert stack.provider.requests == []
