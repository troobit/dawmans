"""Narrowing candidates and the ranked-causes builder (7.2, 7.6–7.8).

The entry path is engine-built end to end (Decision 9): candidates come from
the sidecar entry's causes in the entry's own order, fix pointers are
resolved against the view and filtered through the turn's source scope
(Decision 10), and the terminal `causes[]` preserves the ranking exactly.
The model is not asked for candidates anywhere in this module.
"""

import copy

from corpus_fixtures import (
    make_view,
    passage,
    sidecar_entry,
    triage_source,
    vendor_source,
)

from dawmans.answer.envelope import AnswerEnvelope, Outcome
from dawmans.answer.narrow import (
    build_causes,
    build_narrowing,
    expand_entry,
    matched_entry,
)

LIVE = "ableton/live-12"
SCARLETT = "focusrite/scarlett-solo-4g"
APC = "akai/apc-key-25"
TRIAGE = "authored/triage"

SOURCES = [
    vendor_source(LIVE, LIVE, page_count=1009),
    vendor_source(APC, APC, page_count=5),
    vendor_source(SCARLETT, "focusrite/scarlett-solo", page_count=20),
    triage_source(),
]

# Vendor fix chunks: §16.4 of the Live manual split into two chunks, so one
# section pointer resolves to two passages (the expansion bound is over
# resolved passages, not pointers).
PASSAGES = [
    passage(f"{LIVE}#f1", "The Track Activator mutes the track output"),
    passage(f"{LIVE}#f2", "Click the dimmed track number to re-enable the track"),
    passage(f"{LIVE}#f3", "The MIDI channel selector routes incoming notes"),
    passage(f"{LIVE}#g1", "The cue mix knob feeds the master cue output"),
    passage(f"{APC}#x1", "Hold SHIFT and press a pad to select a scene"),
    passage(f"{SCARLETT}#d1", "The DIRECT MONITOR switch routes input to output"),
    passage(f"{TRIAGE}#t1", "No sound from a track although the meters move"),
    passage(f"{TRIAGE}#t2", "Crackling under load points at the buffer"),
]


def fix(source_id, section, *passage_ids):
    return {"source_id": source_id, "section": section, "passage_ids": list(passage_ids)}


def cause(statement, check, *fixes, flags=()):
    return {
        "statement": statement,
        "check": check,
        "fix": list(fixes),
        "undocumented_device": None,
        "flags": list(flags),
    }


FIVE_CAUSES = [
    cause(
        "The Track Activator is off",
        "the track's number is dimmed in the mixer",
        fix(LIVE, "16.4", f"{LIVE}#f1", f"{LIVE}#f2"),
    ),
    cause(
        "Direct monitoring is on at the interface",
        "the DIRECT MONITOR switch is pushed in",
        fix(SCARLETT, "3.1", f"{SCARLETT}#d1"),
    ),
    cause(
        "The cue mix is fully dry",
        "the cue knob sits at its left stop",
        fix(LIVE, "16.5", f"{LIVE}#g1"),
    ),
    cause(
        "The MIDI channel does not match",
        "the channel selector shows a different channel",
        fix(LIVE, "17.1", f"{LIVE}#f3"),
    ),
    cause(
        "A fifth cause past the band",
        "a check that must never appear",
        fix(LIVE, "18.0", f"{LIVE}#f1"),
    ),
]


def entry_view(causes=FIVE_CAUSES, symptom="No sound from a track"):
    return make_view(
        SOURCES,
        PASSAGES,
        sidecar=[
            sidecar_entry(f"{TRIAGE}#t1", [LIVE], symptom=symptom, causes=causes),
            sidecar_entry(f"{TRIAGE}#t2", [LIVE], symptom="Crackling under load"),
        ],
    )


ALL_SELECTED = (TRIAGE, LIVE, APC, SCARLETT)


# --- sidecar lookup ---------------------------------------------------------


def test_matched_entry_is_first_sidecar_hit_in_supplied_order():
    view = entry_view()
    supplied = (f"{LIVE}#f1", f"{TRIAGE}#t2", f"{TRIAGE}#t1")
    assert matched_entry(view, supplied)["passage_id"] == f"{TRIAGE}#t2"


def test_matched_entry_none_when_no_supplied_passage_keys_the_sidecar():
    view = entry_view()
    assert matched_entry(view, (f"{LIVE}#f1", f"{APC}#x1")) is None


def test_expand_entry_none_for_a_passage_without_an_entry():
    view = entry_view()
    assert expand_entry(view, f"{LIVE}#f1", ALL_SELECTED) is None


# --- narrowing provenance (Decision 9, 7.2) ---------------------------------


def test_candidates_are_the_first_four_causes_in_entry_order():
    view = entry_view()
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    narrowing = build_narrowing(expansion)
    assert [(c.label, c.value) for c in narrowing.candidates] == [
        (member["check"], member["statement"]) for member in FIVE_CAUSES[:4]
    ]


def test_a_two_cause_entry_yields_both_candidates():
    view = entry_view(causes=FIVE_CAUSES[:2])
    narrowing = build_narrowing(expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED))
    assert [c.value for c in narrowing.candidates] == [
        member["statement"] for member in FIVE_CAUSES[:2]
    ]


def test_the_question_names_the_symptom():
    view = entry_view(symptom="No sound from a track")
    narrowing = build_narrowing(expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED))
    assert "No sound from a track" in narrowing.question


def test_each_candidate_maps_to_its_own_cause_and_fix():
    # 7.7 is structural on the entry path: every candidate is one cause
    # carrying its own check and its own fix pointer, so selecting it
    # changes what is retrieved or reported.
    view = entry_view()
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    narrowing = build_narrowing(expansion)
    assert len(narrowing.candidates) == len(expansion.causes)
    checks = [c.check for c in expansion.causes]
    fixes = [c.fix_in_scope for c in expansion.causes]
    assert len(set(checks)) == len(checks)
    assert len(set(fixes)) == len(fixes)


# --- fix-pointer scope (Decision 10) ----------------------------------------


def test_no_admitted_fix_lies_outside_the_selected_set():
    view = entry_view()
    selected = (TRIAGE, LIVE)
    expansion = expand_entry(view, f"{TRIAGE}#t1", selected)
    for passage_id in expansion.admitted:
        assert view.passages_by_id[passage_id]["source_id"] in selected


def test_an_out_of_scope_fix_carries_the_cause_as_unbacked_and_names_the_source():
    view = entry_view()
    expansion = expand_entry(view, f"{TRIAGE}#t1", (TRIAGE, LIVE))
    monitoring = expansion.causes[1]  # its only fix lives in the Scarlett manual
    assert monitoring.fix_cites == ()
    assert monitoring.unbacked_for_turn
    assert monitoring.out_of_scope_sources == (SCARLETT,)
    assert SCARLETT in expansion.suggested_source_ids


def test_everything_backed_when_every_fix_source_is_selected():
    view = entry_view()
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    assert not expansion.suggested_source_ids
    for member in expansion.causes:
        assert member.fix_cites
        assert not member.unbacked_for_turn


# --- the expansion bound ----------------------------------------------------


def test_a_section_pointer_admits_every_chunk_it_produced():
    view = entry_view()
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    assert expansion.causes[0].fix_cites == (f"{LIVE}#f1", f"{LIVE}#f2")


def test_excess_drops_in_cause_order_within_a_cause_in_section_order():
    view = entry_view()
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED, cap=3)
    # Cause 1 keeps both §16.4 chunks, cause 2 gets the third slot, causes
    # 3 and 4 are dropped whole — and a cap-dropped fix leaves the cause
    # unbacked for the turn, exactly as an out-of-scope one does.
    assert expansion.admitted == (f"{LIVE}#f1", f"{LIVE}#f2", f"{SCARLETT}#d1")
    assert expansion.causes[2].fix_cites == ()
    assert expansion.causes[2].unbacked_for_turn
    assert expansion.causes[3].fix_cites == ()


def test_already_supplied_counts_against_the_cap_and_is_not_readmitted():
    view = entry_view()
    already = (f"{TRIAGE}#t1", f"{LIVE}#f1")
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED, already_supplied=already, cap=3)
    # Budget is cap minus what retrieval already supplied: one slot. #f1 is
    # cited without being re-admitted; #f2 takes the slot; nothing follows.
    assert expansion.admitted == (f"{LIVE}#f2",)
    assert expansion.causes[0].fix_cites == (f"{LIVE}#f1", f"{LIVE}#f2")
    assert expansion.causes[1].fix_cites == ()


def test_a_fix_shared_by_two_causes_is_admitted_once_and_cited_by_both():
    shared = [
        cause("First cause", "first check", fix(LIVE, "16.4", f"{LIVE}#f1")),
        cause("Second cause", "second check", fix(LIVE, "16.4", f"{LIVE}#f1")),
    ]
    view = entry_view(causes=shared)
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    assert expansion.admitted == (f"{LIVE}#f1",)
    assert expansion.causes[0].fix_cites == (f"{LIVE}#f1",)
    assert expansion.causes[1].fix_cites == (f"{LIVE}#f1",)


# --- state-value suppression (7.8) ------------------------------------------


def test_a_supplied_state_value_removes_its_candidate():
    view = entry_view()
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    supplied_value = FIVE_CAUSES[1]["statement"]
    narrowing = build_narrowing(expansion, state_supplies=lambda c: c.value == supplied_value)
    assert [c.value for c in narrowing.candidates] == [
        member["statement"] for member in (FIVE_CAUSES[0], FIVE_CAUSES[2], FIVE_CAUSES[3])
    ]


def test_all_candidates_removed_means_no_question():
    view = entry_view()
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    assert build_narrowing(expansion, state_supplies=lambda c: True) is None


def test_one_candidate_left_is_below_the_band_and_asks_nothing():
    # 7.2 fixes the band at 2–4: a one-candidate question discriminates
    # nothing, so the engine answers instead of asking.
    view = entry_view(causes=FIVE_CAUSES[:2])
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    keep = FIVE_CAUSES[0]["statement"]
    assert build_narrowing(expansion, state_supplies=lambda c: c.value != keep) is None


# --- the terminal form (7.6) ------------------------------------------------


def test_causes_are_the_first_four_in_order_with_positional_ranks():
    view = entry_view()
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    causes = build_causes(expansion)
    assert [(c.statement, c.check) for c in causes] == [
        (member["statement"], member["check"]) for member in FIVE_CAUSES[:4]
    ]
    assert [c.rank for c in causes] == [1, 2, 3, 4]


def test_every_cite_resolves_into_the_turn_supplied_set():
    view = entry_view()
    already = (f"{TRIAGE}#t1", f"{LIVE}#f1")
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED, already_supplied=already)
    resolvable = set(already) | set(expansion.admitted)
    for member in build_causes(expansion):
        assert member.cites == (f"{TRIAGE}#t1",)
        assert set(member.fix_cites) <= resolvable


def test_state_suppression_never_drops_a_cause_from_the_terminal_form():
    # 7.6: the entry's ranking is preserved exactly — nothing reorders,
    # merges, adds or drops. Suppression is a narrowing-question concern.
    view = entry_view()
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    assert len(build_causes(expansion)) == 4


def test_causes_construct_a_ranked_causes_envelope():
    view = entry_view()
    causes = build_causes(expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED))
    envelope = AnswerEnvelope(outcome=Outcome.RANKED_CAUSES, causes=causes)
    assert envelope.causes == causes


def test_an_authored_unbacked_cause_is_carried_not_dropped_and_never_mutated():
    causes = [
        cause("A cause with no ingested fix", "an observable check", flags=("unbacked-cause",)),
        cause("A backed cause", "another check", fix(LIVE, "16.4", f"{LIVE}#f1")),
    ]
    view = entry_view(causes=causes)
    entry = view.sidecar[f"{TRIAGE}#t1"]
    before = copy.deepcopy(entry)
    expansion = expand_entry(view, f"{TRIAGE}#t1", ALL_SELECTED)
    built = build_causes(expansion)
    # The engine reads the flag and never sets it: the entry is untouched,
    # the cause stays in the list, and its empty fix_cites is what tells
    # the citation layer to carry the unbacked mark.
    assert entry == before
    assert built[0].fix_cites == ()
    assert expansion.causes[0].unbacked_for_turn
    assert built[1].fix_cites == (f"{LIVE}#f1",)
