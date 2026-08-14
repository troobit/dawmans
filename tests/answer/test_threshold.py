"""The relevance threshold (2.7) and the passage allocation (Decision 5).

τ has two arms, either of which qualifies a candidate: cosine ≥ 0.30, or
BM25 rank 1 within its own source sharing a query term of document
frequency ≤ 5% of the corpus. Qualification is evaluated per source — a
global pool would let the Live manual drown the 5-page APC guide, which is
the case 5.6's floor exists for. Both constants are configuration, not
literals: they are guesses until the evaluation set exists.
"""

import numpy as np
from corpus_fixtures import make_view, passage, vendor_source
from hypothesis import given, settings
from hypothesis import strategies as st

from dawmans.answer.retrieve import RetrievalConfig, retrieve

LIVE = "ableton/live-12"
APC = "akai/apc-key-25"

# 38 Live rows and 2 APC rows: 40 documents, so "midi38" — in one Live row
# and one APC row — has document frequency exactly 5% of the corpus, the ≤
# boundary of the lexical arm. Every Live row shares "compressor" (df 95%).
LIVE_TEXTS = [f"the compressor threshold and ratio controls {i}" for i in range(38)]
LIVE_TEXTS[5] = "midi38 midi38 compressor"  # tf 2: global BM25 rank 1, above the APC hit

SOURCES = [
    vendor_source(LIVE, LIVE, page_count=1009),
    vendor_source(APC, APC, page_count=5),
]
PASSAGES = [passage(f"{LIVE}#l{i:02d}", text) for i, text in enumerate(LIVE_TEXTS)] + [
    passage(f"{APC}#a0", "midi38 pad note mapping"),
    passage(f"{APC}#a1", "pad grid startup overview"),
]
ROWS = {record["passage_id"]: row for row, record in enumerate(PASSAGES)}


def build_view():
    return make_view(SOURCES, PASSAGES)


def query_vector(view, cosines):
    q = np.zeros(len(view.passages), dtype=np.float32)
    for passage_id, cosine in cosines.items():
        q[ROWS[passage_id]] = cosine
    return q


def supplied_ids(result):
    return [member.passage_id for member in result.supplied]


class TestDenseArm:
    def test_cosine_at_the_threshold_qualifies(self):
        view = build_view()
        q = query_vector(view, {f"{APC}#a0": 0.30})

        result = retrieve(view, "zzzz", q, [APC])

        assert result.qualifying_sources == (APC,)
        assert f"{APC}#a0" in supplied_ids(result)

    def test_cosine_below_the_threshold_does_not(self):
        view = build_view()
        q = query_vector(view, {f"{APC}#a0": 0.29})

        result = retrieve(view, "zzzz", q, [APC])

        assert result.qualifying_sources == ()
        assert result.supplied == ()


class TestLexicalArm:
    def test_rank_1_within_its_own_source_qualifies_on_a_rare_shared_term(self):
        # Per-source rank 1, not global. Global rank 1 goes to the Live row
        # holding midi38 twice; the APC hit is global rank 2 — under a
        # global arm the 5-page guide would qualify for nothing and the
        # floor would never fire on it.
        view = build_view()
        q = query_vector(view, {})

        result = retrieve(view, "midi38 compressor", q, [LIVE, APC])

        assert result.pool.bm25[ROWS[f"{APC}#a0"]] < result.pool.bm25[ROWS[f"{LIVE}#l05"]]
        assert set(result.qualifying_sources) == {LIVE, APC}
        assert f"{APC}#a0" in supplied_ids(result)
        assert f"{LIVE}#l05" in supplied_ids(result)

    def test_a_common_shared_term_does_not_qualify(self):
        # Every Live row matches "compressor" with a positive BM25 score,
        # and none of that qualifies anything: the turn is uncovered per
        # 2.1, never synthesised from weak matches.
        view = build_view()
        q = query_vector(view, {})

        result = retrieve(view, "compressor", q, [LIVE, APC])

        assert result.pool.fused  # weak matches exist —
        assert result.supplied == ()  # — and none reaches synthesis
        assert result.qualifying_sources == ()


class TestConstantsAreConfiguration:
    def test_the_dense_arm_reads_the_configured_threshold(self):
        view = build_view()
        q = query_vector(view, {f"{APC}#a0": 0.40})

        default = retrieve(view, "zzzz", q, [APC])
        raised = retrieve(view, "zzzz", q, [APC], config=RetrievalConfig(dense_tau=0.50))

        assert f"{APC}#a0" in supplied_ids(default)
        assert raised.supplied == ()

    def test_the_lexical_arm_reads_the_configured_df_share(self):
        view = build_view()
        q = query_vector(view, {})

        default = retrieve(view, "midi38 compressor", q, [LIVE, APC])
        tightened = retrieve(
            view, "midi38 compressor", q, [LIVE, APC], config=RetrievalConfig(rare_term_df=0.01)
        )

        assert set(default.qualifying_sources) == {LIVE, APC}
        assert tightened.qualifying_sources == ()
        assert tightened.supplied == ()


class TestAllocation:
    def test_one_slot_per_qualifying_source_precedes_fused_rank(self):
        # Ten Live rows qualify hard; the APC row qualifies at the boundary
        # and sits far outside the fused top 8. The floor admits it anyway,
        # and the remaining slots go by fused rank.
        view = build_view()
        cosines = {f"{LIVE}#l{i:02d}": 0.9 for i in range(10)} | {f"{APC}#a0": 0.30}
        q = query_vector(view, cosines)

        result = retrieve(view, "compressor", q, [LIVE, APC])

        ids = supplied_ids(result)
        assert len(ids) == 8
        assert f"{APC}#a0" in ids
        assert sum(1 for pid in ids if pid.startswith(LIVE)) == 7
        # The floor pick keeps its fused position: worst fused rank, last slot.
        assert ids[-1] == f"{APC}#a0"

    def test_qualifying_sources_beyond_12_raise_the_cap_exactly(self):
        # 5.6 takes precedence over 1.3's cap: one passage per qualifying
        # source, and no further passages beyond that.
        view = grid_view([2] * 14)
        q = grid_query(view, 0.5)

        result = retrieve(view, "zzzz", q, [f"v/s{i:02d}" for i in range(14)])

        ids = supplied_ids(result)
        assert len(ids) == 14
        assert len({pid.rsplit("#", 1)[0] for pid in ids}) == 14

    def test_a_narrowing_expansion_caps_at_12(self):
        view = grid_view([10, 6, 4])
        q = grid_query(view, 0.5)
        selected = ["v/s00", "v/s01", "v/s02"]

        plain = retrieve(view, "zzzz", q, selected)
        narrowing = retrieve(view, "zzzz", q, selected, narrowing_expansion=True)

        assert len(plain.supplied) == 8
        assert len(narrowing.supplied) == 12
        for result in (plain, narrowing):
            assert {member.source_id for member in result.supplied} == set(selected)

    @settings(max_examples=40, deadline=None)
    @given(data=st.data())
    def test_floor_cap_precedence_property(self, data):
        # Decision 5, stated executably: |supplied| ≤ max(8, |qualifying|,
        # 12 on a narrowing expansion), every qualifying source contributes
        # ≥ 1, and no qualifying candidate means nothing reaches synthesis.
        counts = data.draw(st.lists(st.integers(1, 3), min_size=1, max_size=15))
        view = grid_view(counts)
        cosines = data.draw(
            st.lists(
                st.sampled_from([0.0, 0.2, 0.5]),
                min_size=len(view.passages),
                max_size=len(view.passages),
            )
        )
        narrowing = data.draw(st.booleans())
        q = np.asarray(cosines, dtype=np.float32)

        result = retrieve(
            view,
            "zzzz",
            q,
            [record["source_id"] for record in view.sources],
            narrowing_expansion=narrowing,
        )

        config = RetrievalConfig()
        qualifying = {
            view.passages[row]["source_id"]
            for row, cosine in enumerate(cosines)
            if cosine >= config.dense_tau
        }
        assert set(result.qualifying_sources) == qualifying
        cap = max(config.base_cap, len(qualifying), config.narrowing_cap if narrowing else 0)
        if not qualifying:
            assert result.supplied == ()
        else:
            assert len(result.supplied) <= cap
            supplied_sources = {member.source_id for member in result.supplied}
            assert qualifying <= supplied_sources
            if len(qualifying) >= cap:
                # The floor fills the raised cap exactly; nothing further.
                assert len(result.supplied) == len(qualifying)


def grid_view(rows_per_source):
    sources = [vendor_source(f"v/s{i:02d}", f"v/s{i:02d}") for i in range(len(rows_per_source))]
    passages = [
        passage(f"v/s{i:02d}#p{j}", f"alpha beta gamma row {i} {j}")
        for i, count in enumerate(rows_per_source)
        for j in range(count)
    ]
    return make_view(sources, passages)


def grid_query(view, cosine):
    return np.full(len(view.passages), cosine, dtype=np.float32)
