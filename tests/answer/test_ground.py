"""Grounding and citation assembly (3.6, 3.7, design §Grounding).

3.6 holds by construction: a Citation is assembled only from an entry in
`supplied`, so the model's text can never become one — the round-trip
property attacks exactly that. The ungrounded rule is the CONTRACTS §8
split made executable: fact-shaped tokens (via dawmans.triage.terms,
reused, never reimplemented) and uncited ordered steps fire it; prose
that only orders or eliminates causes over cited facts never does.
"""

from hypothesis import given
from hypothesis import strategies as st

from dawmans.answer import ground
from dawmans.answer.parse import Bullet, Heading, OrderedStep, Paragraph, parse
from dawmans.triage import terms

LIVE = "ableton/live-12"
TRIAGE = "authored/triage"

LIVE_SOURCE = {
    "source_id": LIVE,
    "kind": "vendor-manual",
    "display_name": "Live 12 manual",
    "doc_version": "12.0",
    "hardware_applicability": {"device": LIVE, "status": "confirmed"},
}
TRIAGE_SOURCE = {
    "source_id": TRIAGE,
    "kind": "authored-triage",
    "display_name": "Triage notes",
    "hardware_applicability": {"status": "assumed"},
}

LIVE_PASSAGE = {
    "passage_id": f"{LIVE}#a1",
    "source_id": LIVE,
    "section_number": "16.4",
    "section_title": "Track Activator",
    "page_start": 312,
    "page_end": 313,
    "text": "The Track Activator mutes the track output",
    "degraded": True,
    "has_figures": True,
}
TRIAGE_PASSAGE = {
    "passage_id": f"{TRIAGE}#t1",
    "source_id": TRIAGE,
    "section_title": "No sound from a track",
    "text": "No sound from a track although the meters move",
    "unbacked": True,
    "entry_location": "triage/no-sound.md:12",
}

SUPPLIED = {record["passage_id"]: record for record in (LIVE_PASSAGE, TRIAGE_PASSAGE)}
SOURCES = {LIVE: LIVE_SOURCE, TRIAGE: TRIAGE_SOURCE}


def paragraph(text):
    return Paragraph(text=text, markers=ground.markers_in(text))


def step(text, number=1):
    return OrderedStep(number=number, text=text, markers=ground.markers_in(text))


class TestCitationRoundTrip:
    """For any supplied set and any stream of markers drawn from supplied
    and unknown: every Citation resolves to a supplied passage, every
    unknown marker is stripped from the streamed text and counted."""

    supplied_ids = st.sets(st.sampled_from([f"{LIVE}#a1", f"{TRIAGE}#t1"]), max_size=2)
    marker_ids = st.lists(
        st.sampled_from([f"{LIVE}#a1", f"{TRIAGE}#t1", "made/up#x9", f"{LIVE}#gone"]),
        max_size=8,
    )

    @given(supplied_ids=supplied_ids, marker_ids=marker_ids)
    def test_round_trip(self, supplied_ids, marker_ids):
        supplied = {pid: SUPPLIED[pid] for pid in supplied_ids}
        text = "prose " + " and ".join(f"[[p:{pid}]]" for pid in marker_ids)
        blocks = (paragraph(text),)

        result = ground.ground_turn(None, blocks, supplied, SOURCES)

        unknown = [pid for pid in marker_ids if pid not in supplied]
        assert {c.passage_id for c in result.citations} <= set(supplied)
        assert result.stripped == len(unknown)
        for pid in unknown:
            assert f"[[p:{pid}]]" not in result.body[0].text
        for pid in marker_ids:
            if pid in supplied:
                assert f"[[p:{pid}]]" in result.body[0].text

    def test_citations_are_deduped_in_first_appearance_order(self):
        blocks = (
            paragraph(f"one [[p:{TRIAGE}#t1]] two [[p:{LIVE}#a1]]"),
            paragraph(f"again [[p:{TRIAGE}#t1]]"),
        )
        result = ground.ground_turn(None, blocks, SUPPLIED, SOURCES)
        assert [c.passage_id for c in result.citations] == [f"{TRIAGE}#t1", f"{LIVE}#a1"]

    def test_direct_answer_markers_resolve_and_strip_like_body(self):
        result = ground.ground_turn(
            f"Do the thing. [[p:{LIVE}#a1]] [[p:made/up#x9]]", (), SUPPLIED, SOURCES
        )
        assert f"[[p:{LIVE}#a1]]" in result.direct_answer
        assert "made/up" not in result.direct_answer
        assert result.stripped == 1
        assert [c.passage_id for c in result.citations] == [f"{LIVE}#a1"]


class TestFieldCopy:
    """3.2/3.3/3.8: a field copy from Passage and SourceRecord —
    nothing synthesised, nothing dropped."""

    def test_vendor_citation_carries_every_field(self):
        citation = ground.build_citation(LIVE_PASSAGE, LIVE_SOURCE)
        assert citation.passage_id == f"{LIVE}#a1"
        assert citation.source_id == LIVE
        assert citation.display_name == "Live 12 manual"
        assert citation.kind == "vendor-manual"
        assert citation.doc_version == "12.0"
        assert citation.hardware_applicability == "confirmed"
        assert citation.section_number == "16.4"
        assert citation.section_title == "Track Activator"
        assert citation.page == 312
        assert citation.degraded is True
        assert citation.has_figures is True
        assert citation.unbacked is False
        assert citation.entry_location is None

    def test_has_figures_is_the_bool_the_corpus_publishes(self):
        # Regression, found by asking the real index a real question rather
        # than by reading the record: `data/manual-corpus` sets this from
        # `any(unit.flags.has_figures …)`, so what arrives is `True`/`False`
        # and never a list of pages. This package modelled it as a tuple and
        # built the citation with `tuple(...)`, which raised TypeError on the
        # first vendor passage carrying a figure and killed the turn
        # mid-stream. `ui`'s records.ts types it `boolean`, so the bool is
        # also what the surface reads.
        for published, expected in ((True, True), (False, False)):
            citation = ground.build_citation(
                {**LIVE_PASSAGE, "has_figures": published}, LIVE_SOURCE
            )
            assert citation.has_figures is expected

    def test_a_passage_with_no_has_figures_key_is_not_figured(self):
        passage = {name: value for name, value in LIVE_PASSAGE.items() if name != "has_figures"}
        assert ground.build_citation(passage, LIVE_SOURCE).has_figures is False

    def test_pageless_citation_fields_are_absent_never_empty(self):
        # The pageless-citation property: absent is None — never an empty
        # string, never synthesised (the Citation record enforces it too).
        citation = ground.build_citation(TRIAGE_PASSAGE, TRIAGE_SOURCE)
        assert citation.kind == "authored-triage"
        assert citation.doc_version is None
        assert citation.section_number is None
        assert citation.page is None
        assert citation.section_title == "No sound from a track"  # the symptom, in the slot
        assert citation.entry_location == "triage/no-sound.md:12"
        assert citation.hardware_applicability == "assumed"
        assert citation.unbacked is True

    def test_unbacked_for_turn_marks_a_backed_passage(self):
        # 7.6 / Decision 10: empty fix_cites[] means the cause's citation
        # carries unbacked for this turn — a reading, never a mutation.
        citation = ground.build_citation(LIVE_PASSAGE, LIVE_SOURCE, unbacked_for_turn=True)
        assert citation.unbacked is True
        assert LIVE_PASSAGE.get("unbacked") is None  # the record is untouched


class TestUngroundedRule:
    """The deterministic 3.7 rule, per block, and the §8 split."""

    def test_the_term_extractor_is_dawmans_triage_terms(self):
        # Reused, never reimplemented — the two specs cannot drift on what
        # counts as a product term.
        assert ground.terms is terms

    def test_uncited_capitalised_run_is_ungrounded(self):
        assert ground.is_ungrounded(paragraph("Turn the Track Activator off"), SUPPLIED)

    def test_uncited_numeric_literal_is_ungrounded(self):
        assert ground.is_ungrounded(paragraph("set the rate to 44.1 kHz"), SUPPLIED)

    def test_uncited_menu_path_is_ungrounded(self):
        assert ground.is_ungrounded(paragraph("open options > preferences > audio"), SUPPLIED)
        assert ground.is_ungrounded(paragraph("open options → preferences"), SUPPLIED)

    def test_an_uncited_ordered_step_is_ungrounded_without_any_fact_token(self):
        # Arm (b): "Click it to re-enable the track" carries no numeral,
        # no capitalised run, no menu path — and is exactly what the user
        # acts on, so arm (a) alone would let it through.
        block = step("Click it to re-enable the track.")
        assert not ground.fact_shaped(block.text)
        assert ground.is_ungrounded(block, SUPPLIED)

    def test_a_cited_block_is_never_ungrounded(self):
        assert not ground.is_ungrounded(
            step(f"Click it to re-enable the track. [[p:{LIVE}#a1]]"), SUPPLIED
        )
        assert not ground.is_ungrounded(
            paragraph(f"Turn the `Track Activator` off. [[p:{LIVE}#a1]]"), SUPPLIED
        )

    def test_a_marker_outside_supplied_does_not_ground_a_block(self):
        assert ground.is_ungrounded(
            paragraph("Turn the Track Activator off. [[p:made/up#x9]]"), SUPPLIED
        )

    def test_reasoning_prose_over_cited_facts_is_never_marked(self):
        # A prose block that only orders or eliminates causes, in ordinary
        # lower-case words: no fact-shaped token, not a step — the
        # CONTRACTS §8 split made executable.
        block = paragraph(
            "since the meters move, the first two causes are unlikely; "
            "check the monitoring path before the routing."
        )
        assert not ground.is_ungrounded(block, SUPPLIED)

    def test_ungrounded_is_evaluated_per_block_over_the_turn(self):
        cited = paragraph(f"The `Track Activator` mutes the track. [[p:{LIVE}#a1]]")
        uncited = step("Click it to re-enable the track.")
        assert ground.ground_turn(None, (cited,), SUPPLIED, SOURCES).ungrounded is False
        assert ground.ground_turn(None, (cited, uncited), SUPPLIED, SOURCES).ungrounded is True

    def test_a_block_with_no_letters_is_never_fact_shaped(self):
        # Regression from the first real turns: a model that numbers its
        # sections `## 2.` produces a heading whose whole content is `2.`,
        # and the numeric class matched the bare digit. Every one of the
        # five starter symptoms came back flagged ungrounded while every
        # prose block in them was cited.
        for marker in ("2.", "3.", "1)", "—", "  4. "):
            assert not ground.fact_shaped(marker)
            assert not ground.is_ungrounded(Heading(text=marker, markers=()), SUPPLIED)

    def test_a_numeral_beside_words_is_still_fact_shaped(self):
        # The narrowing is "no letters at all", not "no bare numerals":
        # 7.3's mandated cause turns on an output running above 0 dB, and
        # that claim is exactly what arm (a) exists to catch.
        assert ground.fact_shaped("set the output to 0 dB")
        assert ground.is_ungrounded(paragraph("raise the buffer to 512 samples"), SUPPLIED)

    def test_bullets_follow_arm_a_not_arm_b(self):
        # Arm (b) is ordered steps only; a bullet with no fact-shaped
        # token is not an instruction from nowhere.
        text = "check the obvious things first"
        assert not ground.is_ungrounded(Bullet(text=text, markers=()), SUPPLIED)


class TestHistoryNonCitability:
    """10.3: markers appearing in history text never produce a Citation —
    grounding scans only the turn's output, and only against supplied."""

    @given(st.text(max_size=200))
    def test_history_text_never_reaches_citations(self, history_text):
        # History enters the prompt in an uncitable block and is never an
        # input to grounding; the property that makes that airtight is
        # that assembly ranges over supplied alone, whatever text exists.
        history = f"Q: earlier\nA: see [[p:{LIVE}#gone]] {history_text}"
        stream = f"answered\nDirect answer here.\n---\nProse echoing [[p:{LIVE}#gone]]."
        parsed = parse(stream, covered=True)
        result = ground.ground_turn(parsed.direct_answer, parsed.body, SUPPLIED, SOURCES)
        assert f"{LIVE}#gone" not in {c.passage_id for c in result.citations}
        assert "gone" not in result.body[0].text
        assert history  # history exists and contributed nothing


class TestStateNonCitability:
    """8.6: a state value is never in supplied, so a marker naming one is
    stripped and counted — the structural half, beside the prompt-level
    attribution direction."""

    def test_a_state_key_marker_never_produces_a_citation(self):
        result = ground.ground_turn(
            None, (paragraph("Monitor is off [[p:track.3.monitor]]"),), SUPPLIED, SOURCES
        )
        assert result.citations == ()
        assert result.stripped == 1
        assert "track.3.monitor" not in result.body[0].text
