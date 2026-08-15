"""The term check — design 'The term check (2.6)'.

Extraction runs over the **cause statement plus its `check:` value** and nothing
else, and containment runs against the passages the cause's pointers resolve to.
Every passage here comes from the committed section fixtures, so nothing opens a
PDF or loads the embedding model.

A miss is a flag and never `unbacked` (Decision 5): 2.4 and 8.5 stay the only two
producers of that mark.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fixture_rig import RIG
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from rendering import Section, entry_file
from sections import CORPUS, passages

from dawmans.triage.model import Cause, DeviceRef, Entry
from dawmans.triage.parse import parse_entry
from dawmans.triage.terms import (
    Resolution,
    check_terms,
    device_vocabulary,
    term_flag,
    terms,
)

ENTRY_PATH = Path("triage/no-sound-from-track.md")

LIVE_ID = "ableton/live-12"
SCARLETT_ID = "focusrite/scarlett-solo-4g"

POINTER = f"{LIVE_ID} §18.6"

FILLER = Section("Another cause entirely", check="look at something else", fixes=[POINTER])
"""1.4's floor is two causes, so every fixture needs a second one to parse."""


# --- Building an entry and reaching one cause ------------------------------


def entry_with(
    statement: str,
    check: str,
    *,
    notes: list[str] | None = None,
    devices: list[str] | None = None,
    preamble: list[str] | None = None,
    closing: str | None = None,
) -> Entry:
    """A two-cause entry whose **first** cause is the one under test."""
    body = [Section(statement, check=check, fixes=[POINTER], notes=notes or []), FILLER]
    if closing is not None:
        body.append(Section(closing))
    text = entry_file(
        devices=devices or [LIVE_ID],
        symptom="No sound from a track",
        sections=body,
        preamble=preamble,
    )
    result = parse_entry(ENTRY_PATH, text.encode("utf-8"))
    assert result.rejection is None, f"fixture did not parse: {result.rejection}"
    assert result.entry is not None
    return result.entry


def under_test(entry: Entry) -> Cause:
    return entry.causes[0]


def terms_of(
    statement: str, check: str, *, display_names: list[str] | None = None, **kw
) -> list[str]:
    entry = entry_with(statement, check, **kw)
    return terms(entry, under_test(entry), display_names=display_names or [])


def misses(
    statement: str,
    check: str,
    resolutions: list[Resolution],
    *,
    display_names: list[str] | None = None,
    **kw,
):
    entry = entry_with(statement, check, **kw)
    return check_terms(entry, under_test(entry), resolutions, display_names=display_names or [])


# --- Sections of the real index, as the term check sees them ---------------

ROWS = passages(*CORPUS)


def section(source_id: str, *, number: str | None = None, title: str | None = None) -> Resolution:
    """One section's passages, in section order — what a pointer resolves to."""
    rows = [
        row
        for row in ROWS
        if row["source_id"] == source_id
        and (number is None or row["section_number"] == number)
        and (title is None or row["section_title"] == title)
    ]
    assert rows, f"no such section in the fixtures: {source_id} {number or title}"
    label = f"{source_id} §{number}" if number else f'{source_id} "{title}"'
    return Resolution(label=label, texts=tuple(str(row["text"]) for row in rows))


SOLOING = section(LIVE_ID, number="18.6")
"""Prints `Track Activator`, `Cue Out` and `Solo`."""

MIXER_EXTRAS = section(LIVE_ID, number="18.1.1")
"""Prints `0 dB` — the section 7.3's gain-stage cause depends on."""

SATURATOR = section(LIVE_ID, number="28.34")
DRUM_BUSS = section(LIVE_ID, number="28.12")
LIMITER = section(LIVE_ID, number="28.24")
"""Chunked into three: `Limiter` and `Ceiling` are in the first, `True Peak` in the third."""

DIRECT_MONITOR = section(SCARLETT_ID, title="Direct Monitor Button")


# --- The checked span (the deliberate narrowing of 2.6) --------------------


def test_the_span_is_the_cause_statement_and_its_check():
    assert terms_of("The Track Activator is off", "look at the Cue Out chooser") == [
        "Track Activator",
        "Cue Out",
    ]


def test_a_why_line_is_excluded_from_the_span():
    """2.5 entitles the author to an unsupported *causal* assertion, and `why:` is
    where that assertion is written. The risk is named in the design rather than
    hidden: a factual claim written into a `why:` line escapes the check."""
    assert (
        terms_of(
            "the track is silent",
            "watch the meter",
            notes=["why: the Cue Out chooser is routed elsewhere"],
        )
        == []
    )


def test_loose_prose_in_a_cause_is_excluded_from_the_span():
    assert (
        terms_of(
            "the track is silent",
            "watch the meter",
            notes=["The Cue Out chooser is routed elsewhere."],
        )
        == []
    )


def test_the_closing_statement_is_excluded_from_every_cause():
    """It belongs to no cause, so there is no pointer it could be checked against."""
    assert (
        terms_of(
            "the track is silent",
            "watch the meter",
            closing="If none of these apply the Main Out is misrouted",
        )
        == []
    )


# --- Extraction: capitalised runs ------------------------------------------


def test_a_capitalised_run_is_one_term():
    assert terms_of("the Track Activator is off", "watch the meter") == ["Track Activator"]


def test_an_all_caps_run_is_one_term_even_at_a_sentence_start():
    """ALL-CAPS is evidence of a control name in its own right, unlike an initial
    capital, which a sentence start explains on its own."""
    assert terms_of("DIRECT MONITOR is engaged", "listen to the interface") == ["DIRECT MONITOR"]


def test_punctuation_breaks_a_run():
    assert terms_of("the Cue Out, Main Out and Solo are wrong", "look at the panel") == [
        "Cue Out",
        "Main Out",
        "Solo",
    ]


def test_a_single_token_run_at_a_sentence_start_is_dropped():
    """`Live` opening a sentence is capitalised because the sentence opened, not
    because the author is naming a control."""
    assert terms_of("Live is not receiving audio", "the meter is idle") == []


def test_a_sentence_start_token_capitalised_elsewhere_in_the_entry_is_kept():
    """The same word mid-sentence is the corroboration the rule asks for, and it
    may come from anywhere in the entry — here, the preamble."""
    assert terms_of(
        "Live is not receiving audio",
        "the meter is idle",
        preamble=["This starts after the Live set is reopened"],
    ) == ["Live"]


def test_a_sentence_initial_article_is_not_part_of_the_run():
    """The design's own example is `Track Activator`, written by an author as
    "The Track Activator is off": the leading `The` is discounted for exactly the
    reason a single-token run at a sentence start is, and the run starts after it."""
    assert terms_of("The Track Activator is off", "watch the meter") == ["Track Activator"]


def test_a_term_under_three_characters_is_dropped():
    assert terms_of("the EQ is bypassed", "look at the device") == []


# --- Extraction: numeric literals ------------------------------------------


def test_a_numeric_literal_with_its_unit_is_one_term():
    assert terms_of("the output runs above 0 dB", "watch the meter") == ["0 dB"]


@pytest.mark.parametrize("written", ["-12 dB", "44.1 kHz", "100%"])
def test_signed_decimal_and_percentage_literals_are_terms(written: str):
    assert terms_of(f"the level is {written} at the input", "watch the meter") == [written]


def test_a_bare_number_under_three_characters_is_dropped():
    """A count in prose is not a claim about a value the manual prints."""
    assert terms_of("the set has 2 tracks armed", "count them") == []


# --- The declared devices are not terms ------------------------------------

SCARLETT_DEVICE = "focusrite/scarlett-solo"

DISPLAY_NAMES = {device.id: device.display_name for device in RIG}


def test_a_term_equal_to_a_declared_devices_display_name_is_discarded():
    """The device the owner holds, named as `rig.yaml` names it."""
    assert (
        terms_of(
            "the Scarlett Solo is muted",
            "look at the front panel",
            devices=[SCARLETT_DEVICE],
            display_names=[DISPLAY_NAMES[SCARLETT_DEVICE]],
        )
        == []
    )


def test_a_term_equal_to_a_declared_devices_product_token_is_discarded():
    assert (
        terms_of("the Scarlett-Solo is muted", "look at the front panel", devices=[SCARLETT_DEVICE])
        == []
    )


def test_the_device_vocabulary_is_the_id_the_product_token_and_the_display_name():
    """The id form cannot come out of the extractor — a capitalised run carries no
    `/` — so it is asserted here rather than through a cause that could not
    produce it."""
    assert device_vocabulary([DeviceRef(SCARLETT_DEVICE, revision=None)], ["Scarlett Solo"]) == {
        "focusrite/scarlett-solo",
        "scarlett-solo",
        "scarlett solo",
    }


def test_a_device_that_is_not_declared_is_still_a_term():
    """Only the entry's **own** devices are discarded: naming another device's
    control is a factual claim like any other."""
    assert terms_of("the Scarlett Solo is muted", "look at the front panel", devices=[LIVE_ID]) == [
        "Scarlett Solo"
    ]


# --- Containment -----------------------------------------------------------


def test_a_term_the_pointed_at_section_prints_raises_no_flag():
    assert misses("the Track Activator is off", "watch the meter", [SOLOING]) == []


def test_a_term_the_section_does_not_print_is_a_miss_naming_the_term_and_the_section():
    """The design's worked example: a cause says `Drum Buss` and points at §28.34
    Saturator, which documents a different device."""
    result = misses("the Drum Buss is doing the damage", "listen to the low end", [SATURATOR])
    assert [miss.term for miss in result] == ["Drum Buss"]
    assert result[0].sections == (SATURATOR.label,)


def test_containment_is_case_sensitive_for_the_capitalised_class():
    """Casefolding would make `Off`, `Monitor` and `MIDI` match almost any prose.
    The cost is real and accepted: the Scarlett's front panel prints
    `DIRECT MONITOR` while its guide prints `Direct Monitor`, and an author who
    copies the hardware gets a flag."""
    assert [miss.term for miss in misses("DIRECT MONITOR is on", "listen", [DIRECT_MONITOR])] == [
        "DIRECT MONITOR"
    ]
    assert misses("the Direct Monitor is on", "listen", [DIRECT_MONITOR]) == []


def test_a_prefix_of_a_printed_word_is_not_containment():
    """Word boundaries, not substrings: §28.12 prints `Drum Buss`, not `Drum Bus`."""
    assert [miss.term for miss in misses("the Drum Bus is overloaded", "listen", [DRUM_BUSS])] == [
        "Drum Bus"
    ]


def test_numeric_containment_is_casefolded():
    """§18.1.1 prints `0 dB`; unit case varies between manuals and even within one."""
    assert misses("the output runs above 0 DB", "watch the meter", [MIXER_EXTRAS]) == []


def test_zero_never_satisfies_ten():
    """Numerals are matched at word boundaries too, or every `0 dB` claim would be
    satisfied by any passage printing a two-digit level."""
    ten = Resolution(label="fixture §1", texts=("The output is limited to 10 dB above nominal.",))
    assert [
        miss.term for miss in misses("the output runs above 0 dB", "watch the meter", [ten])
    ] == ["0 dB"]


# --- Multi-pointer semantics ------------------------------------------------


def test_the_term_check_sees_a_split_sections_concatenation():
    """§28.24 packs into three passages. `Limiter` and `Ceiling` are in the first
    and `True Peak` in the third; which chunk holds a control name is an artefact
    of the word cap and changes under a re-chunk."""
    assert len(LIMITER.texts) == 3
    statement = "the Ceiling and True Peak settings are wrong"
    assert misses(statement, "look at the Limiter", [LIMITER]) == []


def test_any_pointers_resolution_set_satisfies_a_term():
    """A term backed by one of two cited sections is backed."""
    assert misses("the Drum Buss is doing the damage", "listen", [SATURATOR, DRUM_BUSS]) == []
    assert misses("the Drum Buss is doing the damage", "listen", [DRUM_BUSS, SATURATOR]) == []


def test_a_miss_names_every_section_that_was_checked():
    result = misses("the Drum Bus is overloaded", "listen", [SATURATOR, DRUM_BUSS])
    assert result[0].sections == (SATURATOR.label, DRUM_BUSS.label)


def test_a_cause_with_no_pointer_is_not_term_checked():
    """2.3's carve-out leaves nothing to check against, and flagging every term of
    an already-unbacked cause would be noise on top of the mark it already carries."""
    assert misses("the Drum Buss is doing the damage", "listen", []) == []


# --- The flag (Decision 5) --------------------------------------------------


def test_the_flag_names_the_term_the_section_the_symptom_and_the_cause():
    entry = entry_with("the Drum Buss is doing the damage", "listen to the low end")
    cause = under_test(entry)
    (miss,) = check_terms(entry, cause, [SATURATOR])
    flag = term_flag(entry, cause, miss)
    assert flag.name == "term-not-in-passage"
    assert flag.source_file == ENTRY_PATH
    assert flag.symptom == entry.symptom
    assert flag.cause == cause.statement
    assert "Drum Buss" in flag.detail
    assert SATURATOR.label in flag.detail


def test_a_miss_never_sets_unbacked():
    """Decision 5. What failed is a heuristic over an author's prose whose
    false-positive rate cannot be bounded; the pointer itself resolved. 2.4 and
    8.5 remain the only two producers of `unbacked`."""
    entry = entry_with("the Drum Buss is doing the damage", "listen to the low end")
    cause = under_test(entry)
    names = {term_flag(entry, cause, miss).name for miss in check_terms(entry, cause, [SATURATOR])}
    assert names == {"term-not-in-passage"}


# --- Property: soundness, one direction only --------------------------------

_LIFTABLE = re.compile(r"\b[A-Z][A-Za-z']*(?: [A-Z][A-Za-z']*)*\b")
"""Capitalised runs, found independently of `terms.py`'s own extractor.

Stating the property against the module's extractor would assert only that it
agrees with itself.
"""


def _liftable(text: str) -> list[str]:
    return [
        match.group()
        for line in text.split("\n")
        for match in _LIFTABLE.finditer(line)
        if len(match.group()) >= 3
    ]


@st.composite
def _lifted_phrases(draw: st.DrawFn) -> tuple[str, str]:
    """A passage of the real index, and a capitalised phrase printed in it."""
    row = draw(st.sampled_from(ROWS))
    phrases = _liftable(str(row["text"]))
    assume(phrases)
    return str(row["text"]), draw(st.sampled_from(phrases))


@given(_lifted_phrases())
@settings(max_examples=200)
def test_terms_lifted_verbatim_from_a_pointed_at_passage_never_flag(case: tuple[str, str]):
    """Term-check soundness. Stated in one direction only, deliberately: recall is
    a heuristic, not an invariant, and asserting it would pin the extractor's
    false-negative rate as if it were a contract."""
    text, phrase = case
    resolution = Resolution(label="fixture §1", texts=(text,))
    statement = f"the {phrase} is not set correctly"
    assert misses(statement, "check the device panel", [resolution]) == []
