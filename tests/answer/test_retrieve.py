"""Masked hybrid retrieval and RRF fusion — design §Retrieval and Decision 1.

Masking precedes top-k on both retrievers: out-of-scope and device-filtered
rows never consume the depth slots, so a narrow scope against a large manual
cannot look like poor coverage. The fusion properties are the arithmetic
Decision 1 rests on, stated executably.
"""

import socket

import numpy as np
from corpus_fixtures import (
    make_view,
    passage,
    sidecar_entry,
    triage_source,
    vendor_source,
)
from hypothesis import given, settings
from hypothesis import strategies as st

from dawmans.answer.retrieve import (
    QUERY_PREFIX,
    RetrievalConfig,
    candidate_mask,
    candidate_pool,
    embed_query,
    fuse,
)
from dawmans.answer.scope import device_scope

LIVE = "ableton/live-12"
APC = "akai/apc-key-25"
TRIAGE = "authored/triage"

SOURCES = [
    vendor_source(LIVE, LIVE, page_count=1009),
    vendor_source(APC, APC, page_count=5),
    triage_source(),
]

# The Live rows match "warp" hard (tf 3) so an unmasked lexical top-k would
# be all Live; the triage rows match harder still and declare a device with
# no manual, so the device filter must remove them before top-k too.
PASSAGES = (
    [passage(f"{LIVE}#l{i:02d}", f"warp warp warp modes stretch audio clip {i}") for i in range(12)]
    + [passage(f"{APC}#a{i}", f"warp the pad grid overview {i}") for i in range(3)]
    + [passage(f"{TRIAGE}#t{i}", f"warp warp warp warp console bus {i}") for i in range(2)]
)

SIDECAR = [
    sidecar_entry(f"{TRIAGE}#t{i}", ["behringer/x32"]) for i in range(2)
]

ROWS = {record["passage_id"]: row for row, record in enumerate(PASSAGES)}


def build_view():
    return make_view(SOURCES, PASSAGES, sidecar=SIDECAR)


def query_vector(view, cosines):
    """One-hot rows make `vectors @ q` read q's component per row."""
    q = np.zeros(len(view.passages), dtype=np.float32)
    for passage_id, cosine in cosines.items():
        q[ROWS[passage_id]] = cosine
    return q


def source_of(passage_id):
    return passage_id.rsplit("#", 1)[0]


class TestCandidateMask:
    def test_the_mask_covers_exactly_the_selected_sources_rows(self):
        view = build_view()
        scope = device_scope(view, [APC])

        mask = candidate_mask(view, [APC], scope)

        assert sorted(np.flatnonzero(mask)) == [ROWS[f"{APC}#a{i}"] for i in range(3)]

    def test_device_filtered_rows_are_removed_from_the_mask(self):
        view = build_view()
        scope = device_scope(view, [LIVE, TRIAGE])

        mask = candidate_mask(view, [LIVE, TRIAGE], scope)

        # The triage rows declare behringer/x32, disjoint from the scope:
        # excluded from the turn entirely, not merely ranked lower.
        assert not any(mask[ROWS[f"{TRIAGE}#t{i}"]] for i in range(2))
        assert all(mask[ROWS[f"{LIVE}#l{i:02d}"]] for i in range(12))

    def test_one_source_and_all_sources_are_the_same_mask_path(self):
        # 5.4 and 5.8 have no special case: a multi-selection mask is the
        # union of the single-selection masks, the mask just narrower or
        # wider. Vendor-only, so the device scope does not vary the rows.
        view = make_view(SOURCES[:2], PASSAGES[:15])

        single = candidate_mask(view, [LIVE], device_scope(view, [LIVE])) | candidate_mask(
            view, [APC], device_scope(view, [APC])
        )
        combined = candidate_mask(view, [LIVE, APC], device_scope(view, [LIVE, APC]))

        assert np.array_equal(single, combined)


class TestMaskPrecedesTopK:
    def test_dense_slots_are_never_consumed_by_out_of_scope_rows(self):
        view = build_view()
        # Every Live row outscores every APC row, and the depth is smaller
        # than the Live pool: retrieve-then-mask would return nothing.
        q = query_vector(
            view,
            {f"{LIVE}#l{i:02d}": 0.9 for i in range(12)} | {f"{APC}#a{i}": 0.5 for i in range(3)},
        )

        pool = candidate_pool(view, "zzzz", q, [APC], config=RetrievalConfig(depth=2))

        assert len(pool.dense) == 2
        assert all(source_of(pid) == APC for pid in pool.dense)
        assert pool.fused and all(source_of(pid) == APC for pid in pool.fused)

    def test_lexical_slots_are_never_consumed_by_out_of_scope_rows(self):
        view = build_view()
        q = query_vector(view, {})

        pool = candidate_pool(view, "warp", q, [APC], config=RetrievalConfig(depth=2))

        # Unmasked, the tf-3 Live rows fill every slot; the mask is a weight
        # mask applied before top-k, so the APC rows fill the depth instead.
        assert len(pool.lexical) == 2
        assert all(source_of(pid) == APC for pid in pool.lexical)

    def test_device_filtered_rows_never_consume_lexical_slots(self):
        view = build_view()
        q = query_vector(view, {})

        pool = candidate_pool(
            view, "warp", q, [LIVE, TRIAGE], config=RetrievalConfig(depth=2)
        )

        # The tf-4 triage rows would take both slots were the device filter
        # applied after retrieval.
        assert len(pool.lexical) == 2
        assert all(source_of(pid) == LIVE for pid in pool.lexical)


PIDS = [f"src/p#{i:03d}" for i in range(30)]


class TestFusion:
    @settings(max_examples=200)
    @given(data=st.data())
    def test_monotonicity_improving_a_rank_never_lowers_the_fused_rank(self, data):
        first = data.draw(st.permutations(PIDS))[:15]
        second = data.draw(st.permutations(PIDS))[:15]
        held = data.draw(st.integers(1, len(first) - 1))
        better = data.draw(st.integers(0, held - 1))
        candidate = first[held]
        improved = list(first)
        improved.insert(better, improved.pop(held))

        before = fuse([first, second]).index(candidate)
        after = fuse([improved, second]).index(candidate)

        assert after <= before

    @settings(max_examples=200)
    @given(data=st.data())
    def test_input_invariance_fused_order_ignores_retriever_order(self, data):
        first = data.draw(st.permutations(PIDS))[:15]
        second = data.draw(st.permutations(PIDS))[:15]

        assert fuse([first, second]) == fuse([second, first])

    def test_ties_break_by_passage_id(self):
        # Two sole hits at the same rank score identically; the order is
        # then the passage_id, not arrival order.
        assert fuse([["b#2"], ["a#1"]]) == ["a#1", "b#2"]
        assert fuse([["a#1"], ["b#2"]]) == ["a#1", "b#2"]

    @settings(max_examples=100)
    @given(
        rank_a=st.integers(13, 50),
        rank_b=st.integers(13, 50),
    )
    def test_decisiveness_a_sole_rank_1_beats_late_double_hits(self, rank_a, rank_b):
        # Decision 1's inequality: 1/(k+1) > 2/(k+r) iff r > k+2. At k=10
        # a sole rank-1 hit outranks every double hit at ranks worse than
        # (12, 12) — the arithmetic the decision rests on, stated executably.
        sole = "sole/hit#1"
        double = "double/hit#1"
        fillers_a = [f"a/f#{i:02d}" for i in range(60)]
        fillers_b = [f"b/f#{i:02d}" for i in range(60)]
        first = [sole] + fillers_a[: rank_a - 2] + [double] + fillers_a[rank_a - 2 : 48]
        second = fillers_b[: rank_b - 1] + [double] + fillers_b[rank_b - 1 : 49]

        fused = fuse([first, second])

        assert fused.index(sole) < fused.index(double)

    def test_the_corpus_caveat_case_reverses_at_k_10(self):
        # The MIDI-38 instance: sole BM25 rank 1 against a (dense 10,
        # lexical 20) consensus chunk. At the published k=60 the consensus
        # chunk wins — the failure the corpus design flagged; at k=10 the
        # decisive hit wins. One arithmetic instance of decisiveness,
        # written as the example Decision 1 argues from.
        sole = "nitro/trigger#38"
        double = "live/consensus#1"
        dense = [f"d/f#{i:02d}" for i in range(9)] + [double]
        lexical = [sole] + [f"l/f#{i:02d}" for i in range(18)] + [double]

        assert fuse([dense, lexical], k=60).index(double) < fuse([dense, lexical], k=60).index(sole)
        assert fuse([dense, lexical], k=10).index(sole) < fuse([dense, lexical], k=10).index(double)


class TestRelevanceAlone:
    def test_ranking_never_weights_a_source_by_its_size(self):
        # Identical corpora except page_count swapped: the fused order must
        # not move (5.5) — ranking is on relevance alone.
        small_apc = [vendor_source(LIVE, LIVE, page_count=1009), vendor_source(APC, APC, page_count=5)]
        big_apc = [vendor_source(LIVE, LIVE, page_count=5), vendor_source(APC, APC, page_count=1009)]
        cosines = {f"{LIVE}#l{i:02d}": 0.4 + 0.01 * i for i in range(12)}
        cosines |= {f"{APC}#a{i}": 0.45 + 0.01 * i for i in range(3)}

        pools = []
        for sources in (small_apc, big_apc):
            view = make_view(sources, PASSAGES[:15])
            q = query_vector(view, cosines)
            pools.append(candidate_pool(view, "warp pad", q, [LIVE, APC]))

        assert pools[0].fused == pools[1].fused


class TestScopeSoundness:
    @settings(max_examples=60, deadline=None)
    @given(
        selected=st.sets(st.sampled_from([LIVE, APC, TRIAGE]), min_size=1),
        components=st.lists(
            st.floats(0.0, 1.0, allow_nan=False), min_size=17, max_size=17
        ),
        question=st.sampled_from(["warp", "pad grid", "console bus", "zzzz"]),
    )
    def test_no_candidate_leaves_the_selected_or_device_scope(
        self, selected, components, question
    ):
        view = build_view()
        selected = sorted(selected)
        scope = device_scope(view, selected)
        q = np.asarray(components, dtype=np.float32)

        pool = candidate_pool(view, question, q, selected)

        for pid in pool.fused:
            assert source_of(pid) in selected
            entry = view.sidecar.get(pid)
            if entry is not None and entry["devices"]:
                assert {member["id"] for member in entry["devices"]} & scope


class TestQueryEmbedding:
    class RecordingEmbedder:
        def __init__(self, vector):
            self.vector = vector
            self.texts = None

        def embed(self, texts):
            self.texts = list(texts)
            return [self.vector]

    def test_the_question_carries_the_bge_query_prefix(self):
        # The query prefix, not the passage prefix: passages are embedded
        # bare with their citation header, questions carry the asymmetric
        # BGE instruction (design §Retrieval step 1).
        embedder = self.RecordingEmbedder(np.array([1.0, 0.0]))

        embed_query(embedder, "how do I warp a clip")

        assert QUERY_PREFIX == "Represent this sentence for searching relevant passages: "
        assert embedder.texts == [QUERY_PREFIX + "how do I warp a clip"]

    def test_the_query_vector_is_unit_norm(self):
        embedder = self.RecordingEmbedder(np.array([3.0, 4.0]))

        q = embed_query(embedder, "anything")

        assert np.allclose(np.linalg.norm(q), 1.0)


class TestNoNetwork:
    def test_retrieval_operates_wholly_on_the_loaded_view(self, monkeypatch):
        # No outbound request at any point: sockets are poisoned for the
        # whole retrieval path.
        def refuse(*args, **kwargs):
            raise AssertionError("retrieval attempted a network operation")

        monkeypatch.setattr(socket, "socket", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)

        view = build_view()
        q = query_vector(view, {f"{APC}#a{i}": 0.5 for i in range(3)})
        pool = candidate_pool(view, "warp pad", q, [APC])

        assert pool.fused
