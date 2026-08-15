"""The pointer grammar and section resolution — design 'Fix pointers'.

Resolution runs against a `SectionIndex` built in one pass over a view's
`passages.jsonl`. Everything here builds that index from the committed section
fixtures, so no test opens a PDF or loads the embedding model.
"""

from __future__ import annotations

import pytest
from sections import APC, CORPUS, LIVE, SPLIT, passages

from dawmans.triage.model import Unresolved
from dawmans.triage.pointers import (
    AUTHORED_SOURCE,
    SectionIndex,
    normalise_title,
    parse_pointer,
    resolve,
    title_disagrees,
)

LIVE_ID = "ableton/live-12"
APC_ID = "akai/apc-key-25"
SCARLETT_ID = "focusrite/scarlett-solo-4g"


def index(*names: str) -> SectionIndex:
    return SectionIndex.from_passages(passages(*names or CORPUS))


def pointer(text: str, line: int = 7):
    p = parse_pointer(text, line)
    assert p is not None, f"{text!r} did not parse as a pointer"
    return p


def resolved(text: str, idx: SectionIndex | None = None) -> list[str]:
    outcome = resolve(pointer(text), idx or index())
    assert not isinstance(outcome, Unresolved), f"{text!r} was unresolved: {outcome.reason}"
    return outcome


def unresolved(text: str, idx: SectionIndex | None = None) -> Unresolved:
    outcome = resolve(pointer(text), idx or index())
    assert isinstance(outcome, Unresolved), f"{text!r} resolved to {outcome}"
    return outcome


# --- The three forms ------------------------------------------------------


def test_the_number_form_parses():
    p = pointer(f"{LIVE_ID} §16.4")
    assert (p.source_id, p.section_number, p.section_title) == (LIVE_ID, "16.4", None)


def test_the_title_form_parses():
    p = pointer(f'{APC_ID} "Shift Functions"')
    assert (p.source_id, p.section_number, p.section_title) == (APC_ID, None, "Shift Functions")


def test_both_together_parse():
    p = pointer(f'{LIVE_ID} §16.4 "Soloing and Cueing"')
    assert (p.section_number, p.section_title) == ("16.4", "Soloing and Cueing")


def test_the_line_is_carried_for_the_message():
    assert pointer(f"{LIVE_ID} §16.4", line=31).line == 31


@pytest.mark.parametrize("text", [LIVE_ID, f"{LIVE_ID} ", f'{LIVE_ID} ""'])
def test_a_source_with_neither_number_nor_title_is_not_a_pointer(text):
    """It addresses nothing, so it is not a pointer at all — parse.py's caller
    reports the cause under `cause-missing-fix` rather than inventing a reason."""
    assert parse_pointer(text, 1) is None


# --- No page form exists (8.1, Decision 3) --------------------------------


@pytest.mark.parametrize(
    "text",
    [
        f"{LIVE_ID} p22",
        f"{LIVE_ID} page 22",
        f"{LIVE_ID} §16.4 p22",
        f"{LIVE_ID} §16.4 page 22",
    ],
)
def test_no_page_form_is_admitted(text):
    """8.1 forbids page-only addressing, and admitting a page even as a qualifier
    would reintroduce the breakage 8.3 exists to avoid. `p22` is therefore not a
    page qualifier that is ignored — it stops the whole thing being a pointer."""
    assert parse_pointer(text, 1) is None


# --- A version change alone breaks nothing (8.3) --------------------------


def test_the_source_id_carries_no_document_version():
    """The token is the source id exactly. Nothing strips a version off it,
    because none is there to strip: `doc_version` lives on the `SourceRecord`,
    which resolution never reads."""
    assert pointer(f"{LIVE_ID} §18.1").source_id == LIVE_ID
    assert unresolved(f"{LIVE_ID}-v12 §18.1").reason == "unknown-source"


def test_a_new_document_version_of_the_same_passages_resolves_identically():
    """8.3: re-ingesting Live 12.1 over Live 12 changes `doc_version` and nothing
    the index is built from. The rows are the only input, so the same rows give
    the same answer — which is why the assertion is about inputs, not versions."""
    rows = passages(LIVE)
    first = resolve(pointer(f"{LIVE_ID} §18.1"), SectionIndex.from_passages(rows))
    second = resolve(pointer(f"{LIVE_ID} §18.1"), SectionIndex.from_passages(list(rows)))
    assert first == second


# --- Resolution: two maps, section order, immutable ------------------------


def test_a_number_resolves_to_its_sections_passages_in_section_order():
    rows = [r for r in passages(LIVE) if r["section_number"] == "18.1"]
    assert resolved(f"{LIVE_ID} §18.1") == [r["passage_id"] for r in rows]


def test_a_pointer_resolves_to_every_chunk_of_a_split_section():
    """§28.24 Limiter packs into three. The cause carries all three and the engine
    cites whichever it retrieves; nothing here picks one, because which chunk holds
    the sentence about the control changes under a re-chunk."""
    split = passages(SPLIT)
    assert len(split) == 3
    assert resolved(f"{LIVE_ID} §28.24") == [r["passage_id"] for r in split]


def test_two_runs_over_one_view_resolve_identically():
    """The index is immutable once built and resolution is pure, so a rebuild in
    the same process — and a second lookup through one index — agree."""
    first, second = index(), index()
    for text in (f"{LIVE_ID} §18.1", f'{APC_ID} "Setup"', f"{LIVE_ID} §28.24"):
        p = pointer(text)
        assert resolve(p, first) == resolve(p, second) == resolve(p, first)


def test_resolution_does_not_mutate_the_index():
    idx = index()
    before = resolved(f"{LIVE_ID} §18.1", idx)
    unresolved(f"{LIVE_ID} §99.99", idx)
    unresolved('never/heard-of-it "Anything"', idx)
    assert resolved(f"{LIVE_ID} §18.1", idx) == before


# --- The title form -------------------------------------------------------


def test_the_title_form_reaches_a_manual_with_no_section_numbers():
    """The APC guide carries no numbering at all, so a number-only syntax could not
    point into a third of the corpus."""
    apc = passages(APC)
    assert all(r["section_number"] is None for r in apc)
    setup = [r["passage_id"] for r in apc if r["section_title"] == "Setup"]
    assert setup
    assert resolved(f'{APC_ID} "Setup"') == setup


@pytest.mark.parametrize(
    "typed",
    ["Setup", "setup", "SETUP", "  Setup  ", "Setup.", "Setup:"],
)
def test_title_normalisation_casefolds_collapses_and_strips_punctuation(typed):
    assert resolved(f'{APC_ID} "{typed}"') == resolved(f'{APC_ID} "Setup"')


def test_a_leading_section_number_is_stripped_from_the_title():
    """Live prints its titles with the number attached, so an author who copies one
    out of the manual types `18.1 The Live Mixer`. That is the same section."""
    assert resolved(f'{LIVE_ID} "18.1 The Live Mixer"') == resolved(f'{LIVE_ID} "The Live Mixer"')


def test_a_unique_prefix_resolves():
    assert resolved(f'{LIVE_ID} "Soloing and"') == resolved(f'{LIVE_ID} "Soloing and Cueing"')


def test_normalise_title_is_what_the_index_is_keyed_on():
    assert normalise_title("  18.1   The Live   Mixer.  ") == normalise_title("the live mixer")


def test_an_ambiguous_prefix_names_its_candidates_and_never_picks_one():
    """Two matches is unresolved with the candidates named. Live duplicates 54 of
    its titles across the outline, so an arbitrary pick would cite the wrong one
    silently."""
    outcome = unresolved(f'{LIVE_ID} "S"')
    assert outcome.reason == "ambiguous-title"
    assert len(outcome.candidates) > 1
    assert outcome.candidates == sorted(outcome.candidates)


def test_an_exact_title_beats_a_prefix_that_would_be_ambiguous():
    """`Limiter` is a whole title and also a prefix of nothing else here; the
    exact map is consulted first, so a title that *is* a section never falls
    through to the prefix rule and never reports itself ambiguous."""
    assert resolved(f'{LIVE_ID} "Limiter"') == resolved(f"{LIVE_ID} §28.24")


def test_a_title_matching_nothing_is_no_such_section_with_nearest_candidates():
    outcome = unresolved(f'{LIVE_ID} "Solong and Queuing"')
    assert outcome.reason == "no-such-section"
    assert "soloing and cueing" in [normalise_title(c) for c in outcome.candidates]


# --- Number selects, title corroborates -----------------------------------


def test_where_both_are_given_the_number_selects():
    """The title is not consulted for selection at all, so a stale title cannot
    move the pointer off the section its number names."""
    assert resolved(f'{LIVE_ID} §28.24 "Soloing and Cueing"') == resolved(f"{LIVE_ID} §28.24")


def test_agreement_raises_no_disagreement():
    assert not title_disagrees(pointer(f'{LIVE_ID} §18.1 "The Live Mixer"'), index())


def test_a_stale_title_beside_a_number_is_the_disagreement_flag():
    """The free renumbering detector: the author wrote both, the manual renumbered,
    and the pair no longer agrees. A flag, not a rejection — the number still
    resolves and the entry is still good."""
    assert title_disagrees(pointer(f'{LIVE_ID} §18.1 "Soloing and Cueing"'), index())


def test_a_title_alone_never_disagrees():
    assert not title_disagrees(pointer(f'{APC_ID} "Setup"'), index())


def test_a_disagreement_on_an_unresolvable_number_is_not_reported():
    """Nothing to disagree with: the number names no section, so the pointer is
    unresolved and the flag would be noise on top of the real message."""
    assert not title_disagrees(pointer(f'{LIVE_ID} §99.99 "The Live Mixer"'), index())


# --- The unresolved reasons -----------------------------------------------


def test_an_unknown_source_is_unknown_source():
    assert unresolved('roland/tr-8s "Anything"').reason == "unknown-source"


def test_a_known_source_with_no_such_number_is_no_such_section():
    assert unresolved(f"{LIVE_ID} §99.99").reason == "no-such-section"


def test_a_pointer_naming_the_authored_source_is_the_authored_target_rejection():
    """2.7. An entry may not cite another entry: the whole grounding discipline
    is that a fix points into a vendor manual."""
    outcome = unresolved(f'{AUTHORED_SOURCE} "No sound from a track"')
    assert outcome.reason == "authored-target"


def test_the_authored_target_is_reported_even_when_the_source_is_absent_from_the_view():
    """The authored source is not in the corpus fixtures at all, so an
    implementation that checked membership first would call this `unknown-source`
    and the entry would get the wrong message."""
    assert AUTHORED_SOURCE not in {r["source_id"] for r in passages(*CORPUS)}
    assert unresolved(f"{AUTHORED_SOURCE} §1").reason == "authored-target"


def test_the_scarlett_resolves_like_any_other_manual():
    """The manual that closed the last corpus gap: 2.3's carve-out admits no
    device now, so the direct-monitoring cause points into it like any other."""
    assert resolved(f'{SCARLETT_ID} "Direct Monitor Button"')
