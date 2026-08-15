"""The chunker and the citation header — 6.2, 6.7-6.11, 7.4-7.5, 12.6, 12.8.

Stage 8 is where the shared `Region`/`Unit` shape becomes the `Passage` records the index is
built from, and it is the whole output of this spec: the design's emission contract says
every `Passage` field comes from exactly one rule, and these tests are that table asserted.

Three of those rules are easy to get subtly wrong and expensive to notice:

- **Page attribution.** A split table's continuation chunk carries a heading copied off p25
  while every row it holds is on p26. Counting the copied heading's page records p25-26, and
  CONTRACTS §3's open-at-page then lands on a page holding none of the rows quoted.
- **The citation header.** It is embedded and BM25-indexed but is not part of
  `Passage.text`, which is what the user is shown when a citation is expanded; repeating it
  there duplicates what the citation already renders.
- **6.11 is a failure, not a rejection.** Rejecting would discard a 1009-page primary source
  over one mis-anchored chunk while reporting the run as succeeded.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from conftest import REPO_ROOT
from dawmans.corpus.chunk import (
    OVERLAP_WORDS,
    TOKEN_MARGIN,
    TOKEN_WINDOW,
    WORD_CAP,
    Chunk,
    PageRangeError,
    check_pages,
    chunk_source,
    citation_header,
    token_budget,
)
from dawmans.corpus.loader import Region, Unit, UnitFlags
from dawmans.records import AUTHORED_SOURCE_ID, HardwareApplicability, SourceRecord

SENTENCE = "The tempo control sets the speed of the transport in beats per minute."
SENTENCE_WORDS = len(SENTENCE.split()) + 1  # plus the marker that makes each one findable


def sentences(count: int, *, mark: str = "s") -> str:
    """`count` sentences of prose, each marked so an ordering fault is visible."""
    return " ".join(f"{mark}{index} {SENTENCE}" for index in range(count))


def words(text: str) -> int:
    return len(text.split())


def record(*, pages: int | None = 40) -> SourceRecord:
    return SourceRecord(
        kind="vendor-manual",
        source_id="alesis/nitro-max",
        vendor="alesis",
        product="nitro-max",
        doctype="manual",
        lang="en",
        doc_version="1",
        display_name="Alesis Nitro Max",
        hardware_applicability=HardwareApplicability(status="assumed", device="alesis/nitro-max"),
        page_count=pages,
        ingested_at="2026-08-15T10:00:00+00:00",
        chunk_count=0,
        low_text=False,
    )


def authored_record() -> SourceRecord:
    return SourceRecord(
        kind="authored-triage",
        source_id=AUTHORED_SOURCE_ID,
        display_name="Triage notes",
        hardware_applicability=HardwareApplicability(status="assumed"),
        ingested_at="2026-08-15T10:00:00+00:00",
        chunk_count=0,
    )


def region(
    *units: Unit,
    number: str | None = "5.2",
    title: str = "MIDI Note Numbers",
    path: tuple[str, ...] = ("Reference",),
    page: int = 25,
    end: int | None = None,
) -> Region:
    return Region(
        section_number=number,
        section_title=title,
        section_path=path,
        page_start=page,
        page_end=end if end is not None else page,
        inferred=False,
        units=list(units),
    )


def entry(*units: Unit, title: str = "No sound from a track") -> Region:
    """One authored entry, as `data/symptom-triage` emits it: pageless, unnumbered, with the
    symptom statement repeated onto every part of a split."""
    return Region(
        section_number=None,
        section_title=title,
        section_path=(),
        page_start=None,
        page_end=None,
        inferred=False,
        units=list(units),
        entry_location="triage/no-sound-from-track.md:7",
    )


def prose(text: str, *, page: int = 25) -> Unit:
    return Unit(text=text, page_start=page, page_end=page)


def row(text: str, *, page: int = 25, heading: bool = False) -> Unit:
    return Unit(text=text, page_start=page, page_end=page, atomic=True, repeat_on_split=heading)


def chunks(source: SourceRecord, *regions: Region) -> list[Chunk]:
    return chunk_source(source, regions)


# --- Property: the cap (6.9, 7.4) --------------------------------------------------------------


@given(
    lengths=st.lists(st.integers(min_value=1, max_value=40), min_size=1, max_size=10),
    atomic=st.lists(st.booleans(), min_size=10, max_size=10),
)
@settings(max_examples=50, deadline=None)
def test_no_chunk_exceeds_the_cap(lengths: list[int], atomic: list[bool]) -> None:
    """6.9. The bound comes from the 512-token retrieval window, not from readability, so an
    over-cap chunk is not untidy: its tail is silently invisible to retrieval while still
    appearing in the text shown to the user (Decision 3)."""
    units = [
        Unit(text=sentences(length, mark=f"u{index}s"), page_start=25, page_end=25, atomic=flag)
        for index, (length, flag) in enumerate(zip(lengths, atomic, strict=False))
    ]

    for chunk in chunks(record(), region(*units)):
        assert words(chunk.passage.text) <= WORD_CAP


def test_an_over_cap_atomic_unit_splits_and_every_part_is_marked() -> None:
    """7.4: a single row longer than the cap is split and each part marked as carrying part
    of one row, rather than left unindexed."""
    huge = row(sentences(WORD_CAP))

    packed = chunks(record(), region(huge))

    assert len(packed) > 1
    assert all(chunk.partial_unit for chunk in packed)
    assert all(words(chunk.passage.text) <= WORD_CAP for chunk in packed)


def test_splitting_ordinary_prose_marks_nothing() -> None:
    """The mark is 7.4's, and 7.4 is about a row. Splitting a long paragraph between chunks
    is 6.8 working as specified, and marking it would make the flag meaningless."""
    packed = chunks(record(), region(prose(sentences(60))))

    assert len(packed) > 1
    assert not any(chunk.partial_unit for chunk in packed)


# --- Property: coverage round-trip (3.1, 6.8) --------------------------------------------------


@given(lengths=st.lists(st.integers(min_value=1, max_value=40), min_size=1, max_size=10))
@settings(max_examples=50, deadline=None)
def test_removing_the_carried_words_reproduces_the_region(lengths: list[int]) -> None:
    """Coverage round-trip over the packing type, which records how many leading words each
    chunk copied in — a repeated heading, or overlap. Removing them and concatenating must
    give the region's own text back, in order: chunking may duplicate text, but it may never
    lose or reorder it."""
    units = [prose(sentences(length, mark=f"u{index}s")) for index, length in enumerate(lengths)]

    packed = chunks(record(), region(*units))

    recovered = [word for chunk in packed for word in chunk.passage.text.split()[chunk.carried :]]
    assert recovered == "\n".join(unit.text for unit in units).split()


# --- Property: region purity (6.7) -------------------------------------------------------------


def test_a_chunk_belongs_to_exactly_one_region() -> None:
    """6.7: a chunk spanning two sections cannot be cited, because the citation names one
    section. Packing therefore restarts at every region boundary."""
    first = region(prose(sentences(4)), number="5.1", title="Connections", page=24)
    second = region(prose(sentences(4)), number="5.2", title="MIDI Note Numbers", page=25)

    identities = {
        (chunk.passage.section_number, chunk.passage.section_title)
        for chunk in chunks(record(), first, second)
    }

    assert identities == {("5.1", "Connections"), ("5.2", "MIDI Note Numbers")}


def test_overlap_never_crosses_a_region_boundary() -> None:
    """Overlapping one would make the citation ambiguous, which 6.7 forbids — and it is what
    confines the blast radius of a vendor edit to one section (Decision 5)."""
    tail = prose(sentences(10, mark="b"))
    first = region(prose(sentences(10, mark="a")), tail, number="5.1", title="Connections", page=24)
    second = region(prose(sentences(4, mark="c")), page=25)

    packed = chunks(record(), first, second)
    opening = next(chunk for chunk in packed if chunk.passage.section_number == "5.2")

    assert opening.carried == 0
    assert opening.passage.text == sentences(4, mark="c")


def test_overlap_carries_a_sentence_boundary_within_a_region() -> None:
    """~50 words snapped to a sentence boundary, so the continuation opens mid-thought
    rather than mid-sentence."""
    packed = chunks(
        record(),
        region(
            prose(sentences(10, mark="a")),
            prose(sentences(10, mark="b")),
            prose(sentences(10, mark="c")),
        ),
    )
    second = packed[1]

    assert len(packed) == 2
    assert 0 < second.carried <= OVERLAP_WORDS
    assert second.carried % SENTENCE_WORDS == 0  # whole sentences, never a part of one
    assert second.passage.text.startswith("b")


def test_overlap_is_suppressed_where_a_unit_repeats_instead() -> None:
    """The repeat already gives the continuity overlap exists to provide, and carrying both
    would put the symptom statement of an authored entry into the hashed text twice
    (`data/symptom-triage` §Passage emission)."""
    symptom = Unit(text="No sound from a track.", repeat_on_split=True)
    causes = [Unit(text=sentences(15, mark=f"c{index}"), atomic=True) for index in range(3)]

    packed = chunks(authored_record(), entry(symptom, *causes))

    assert len(packed) > 1
    for chunk in packed[1:]:
        assert chunk.passage.text.startswith(symptom.text)
        assert chunk.carried == words(symptom.text)


# --- Property: page attribution (6.8) ----------------------------------------------------------


def test_a_split_table_attributes_only_the_pages_its_own_rows_occupy() -> None:
    """6.8, and the failure it prevents: the continuation chunk carries a heading copied off
    p25 while every row it holds is on p26. Recording p25-26 sends open-at-page to a page
    containing none of the rows quoted."""
    heading = row("Trigger | MIDI Note Number", page=25, heading=True)
    first = [row(sentences(4, mark=f"a{index}s"), page=25) for index in range(6)]
    second = [row(sentences(4, mark=f"b{index}s"), page=26) for index in range(6)]

    packed = chunks(record(), region(heading, *first, *second, page=25, end=26))
    tail = packed[-1]

    assert len(packed) == 2
    assert tail.passage.text.startswith(heading.text)
    assert (tail.passage.page_start, tail.passage.page_end) == (26, 26)


def test_overlap_contributes_words_but_not_pages() -> None:
    """The same rule for the other kind of carried text."""
    packed = chunks(
        record(),
        region(
            prose(sentences(10, mark="a"), page=11),
            prose(sentences(10, mark="b"), page=11),
            prose(sentences(10, mark="c"), page=12),
            page=11,
            end=12,
        ),
    )
    second = packed[1]

    assert second.carried > 0
    assert (second.passage.page_start, second.passage.page_end) == (12, 12)


def test_a_unit_spanning_a_page_break_keeps_both_ends() -> None:
    """6.10 forbids splitting a procedure that fits the cap, and a procedure can start on p11
    and end on p12 — which is why `Unit` carries two page fields."""
    procedure = Unit(text=sentences(20), page_start=158, page_end=159, atomic=True)

    (chunk,) = chunks(record(), region(procedure, page=158, end=159))

    assert (chunk.passage.page_start, chunk.passage.page_end) == (158, 159)


# --- Property: atomicity (6.10, 7.4) and heading repetition (7.5) ------------------------------


@given(lengths=st.lists(st.integers(min_value=1, max_value=20), min_size=2, max_size=8))
@settings(max_examples=50, deadline=None)
def test_an_atomic_unit_that_fits_lies_wholly_inside_one_chunk(lengths: list[int]) -> None:
    """6.10 and 7.4: a numbered procedure or a table row that fits the cap is never split."""
    units = [
        Unit(text=sentences(length, mark=f"u{index}s"), page_start=25, page_end=25, atomic=True)
        for index, length in enumerate(lengths)
    ]

    packed = chunks(record(), region(*units))

    for unit in units:
        assert sum(unit.text in chunk.passage.text for chunk in packed) == 1


def test_every_chunk_of_a_split_table_repeats_the_joined_heading() -> None:
    """7.5: without the repeat, a continuation chunk is a list of numbers whose columns are
    named on a page the reader was not given."""
    heading = row("Trigger | MIDI Note Number", heading=True)
    rows = [row(sentences(4, mark=f"r{index}s")) for index in range(12)]

    packed = chunks(record(), region(heading, *rows))

    assert len(packed) > 1
    assert all(chunk.passage.text.startswith(heading.text) for chunk in packed)


def test_a_second_table_repeats_its_own_heading_and_not_the_first() -> None:
    """A region can hold two tables. Accumulating every heading seen so far would prefix the
    second table's rows with the columns of a table they are not in."""
    first_heading = row("Trigger | MIDI Note Number", heading=True)
    second_heading = row("Kit | Program Change", heading=True)

    packed = chunks(
        record(),
        region(
            first_heading,
            *[row(sentences(4, mark=f"a{index}s")) for index in range(6)],
            second_heading,
            *[row(sentences(4, mark=f"b{index}s")) for index in range(6)],
        ),
    )
    tail = packed[-1]

    assert second_heading.text in tail.passage.text
    assert first_heading.text not in tail.passage.text


# --- Property: flag aggregation (5.3, 10.3, 12.6) ----------------------------------------------


@given(
    flags=st.lists(st.tuples(st.booleans(), st.booleans(), st.booleans()), min_size=1, max_size=8)
)
@settings(max_examples=50, deadline=None)
def test_flags_are_the_or_over_the_units_held(flags: list[tuple[bool, bool, bool]]) -> None:
    """The units are atomic, so no overlap is taken and every contributor's whole text is in
    the chunk — which lets the expectation be computed from the region rather than from the
    chunker's own record of what it packed."""
    units = [
        Unit(
            text=sentences(6, mark=f"u{index}s"),
            page_start=25,
            page_end=25,
            atomic=True,
            flags=UnitFlags(degraded=degraded, has_figures=figures, unbacked=unbacked),
        )
        for index, (degraded, figures, unbacked) in enumerate(flags)
    ]

    for chunk in chunks(record(), region(*units)):
        held = [unit for unit in units if unit.text in chunk.passage.text]
        assert chunk.passage.degraded == any(unit.flags.degraded for unit in held)
        assert chunk.passage.has_figures == any(unit.flags.has_figures for unit in held)
        assert chunk.passage.unbacked == any(unit.flags.unbacked for unit in held)


def test_a_chunk_of_degraded_rows_stays_degraded_under_a_clean_heading() -> None:
    """5.3: a flagless copied heading contributes nothing to the OR, which is what stops it
    diluting a flag it does not carry."""
    heading = row("Trigger | MIDI Note Number", heading=True)
    rows = [
        Unit(
            text=sentences(4, mark=f"r{index}s"),
            page_start=25,
            page_end=25,
            atomic=True,
            flags=UnitFlags(degraded=True),
        )
        for index in range(12)
    ]

    packed = chunks(record(), region(heading, *rows))

    assert len(packed) > 1
    assert all(chunk.passage.degraded for chunk in packed)


def test_unbacked_and_entry_location_are_carried_unchanged() -> None:
    """12.6: both are owned by `data/symptom-triage`. This stage neither sets, clears nor
    derives them, and the flag lands only on the passage carrying the unbacked cause."""
    symptom = Unit(text="No sound from a track.", repeat_on_split=True)
    backed = Unit(text=sentences(15, mark="a"), atomic=True)
    flagged = Unit(text=sentences(15, mark="b"), atomic=True, flags=UnitFlags(unbacked=True))

    packed = chunks(authored_record(), entry(symptom, backed, flagged))

    assert [chunk.passage.unbacked for chunk in packed] == [False, True]
    assert {chunk.passage.entry_location for chunk in packed} == {"triage/no-sound-from-track.md:7"}


# --- The citation header -----------------------------------------------------------------------


def test_the_header_is_indexed_and_is_not_part_of_the_passage_text() -> None:
    """The text is what the user is shown when a citation is expanded, and repeating the
    header there duplicates what the citation already renders."""
    (chunk,) = chunks(record(), region(prose(sentences(4))))

    assert chunk.header not in chunk.passage.text
    assert chunk.embedded.startswith(chunk.header)
    assert chunk.passage.text in chunk.embedded


def test_the_numbered_header_carries_the_ancestor_chain() -> None:
    """54 of Live's section titles are duplicated and `Sidechain Parameters` occurs eight
    times. Without the chain that chunk is indexed with the device name nowhere in it, which
    is the exact failure the header exists to prevent."""
    section = region(
        prose(sentences(4)),
        number="28.21.1",
        title="Sidechain Parameters",
        path=("Live's Audio Effects", "Glue Compressor"),
    )

    header = citation_header("Ableton Live 12", section)

    assert header == (
        "Ableton Live 12 — §28.21.1 Live's Audio Effects › Glue Compressor › Sidechain Parameters"
    )


def test_an_unnumbered_header_omits_the_section_marker_entirely() -> None:
    """6.4: the `§` and the number are omitted rather than rendered as `§None`, which is the
    common case on an APC region and on every authored passage."""
    header = citation_header("Akai Apc Key 25", region(prose(sentences(2)), number=None))

    assert header == "Akai Apc Key 25 — Reference › MIDI Note Numbers"
    assert "§" not in header


def test_a_pageless_authored_header_is_the_symptom_alone() -> None:
    """An entry has no ancestor titles and no number; the symptom is the whole of it."""
    header = citation_header("Triage notes", entry(Unit(text=sentences(2))))

    assert header == "Triage notes — No sound from a track"


# --- The token budget (Decision 3) -------------------------------------------------------------


def test_the_budget_names_what_the_word_cap_cannot_guarantee() -> None:
    """A word cap is an estimate of a token bound, and the estimate is worst for exactly the
    content this corpus is full of: serialised table rows run far above the 1.2 tokens per
    word prose averages. The encoded length is measured rather than trusted, which converts
    a silent truncation into a report line."""
    packed = chunks(record(), region(prose(sentences(4))))
    (chunk,) = packed
    identity = chunk.passage.passage_id

    assert token_budget(packed, lambda _: TOKEN_WINDOW - TOKEN_MARGIN - 1) == ([], [])
    assert token_budget(packed, lambda _: TOKEN_WINDOW - TOKEN_MARGIN) == (
        [],
        [(identity, TOKEN_WINDOW - TOKEN_MARGIN)],
    )
    assert token_budget(packed, lambda _: TOKEN_WINDOW) == ([(identity, TOKEN_WINDOW)], [])


def test_the_budget_is_measured_over_the_header_prefixed_text() -> None:
    """The header costs ~15 tokens, ~26 with the ancestor chain, and it is embedded with the
    passage — so measuring the text alone would under-report every chunk."""
    packed = chunks(record(), region(prose(sentences(4))))

    seen: list[str] = []
    token_budget(packed, lambda text: seen.append(text) or 0)

    assert seen == [chunk.embedded for chunk in packed]


def bge_tokeniser() -> Path | None:
    """The cached BGE vocabulary, or None where `make fetch-model` has not been run."""
    return next((REPO_ROOT / "models").rglob("tokenizer.json"), None)


@pytest.mark.skipif(
    bge_tokeniser() is None,
    reason="the BGE tokeniser lives in the models/ cache; populate it with `make fetch-model`",
)
def test_a_maximal_chunk_encodes_under_the_bge_window() -> None:
    """Decision 3's own assertion, against the real tokeniser rather than a stand-in: 350
    words is ~420 tokens, leaving headroom for the citation header and tokeniser variance.
    The model cache is a prerequisite of running ingestion rather than a build step (8.5),
    so this is skipped where it is absent."""
    from tokenizers import Tokenizer

    cache = bge_tokeniser()
    assert cache is not None
    encoder = Tokenizer.from_file(str(cache))
    packed = chunks(record(), region(prose(sentences(WORD_CAP // SENTENCE_WORDS))))

    assert all(words(chunk.passage.text) > WORD_CAP - SENTENCE_WORDS for chunk in packed)
    assert token_budget(packed, lambda text: len(encoder.encode(text).ids)) == ([], [])


# --- 6.11: a chunk page outside the source's page range is a failure ---------------------------


def test_a_chunk_page_outside_the_source_range_is_a_failure() -> None:
    """6.11 says to reject the source; 1.6's closed rejection list does not admit it, and
    rejection would discard a 1009-page primary source over one mis-anchored chunk while
    reporting the run as succeeded. It is a failure instead: the previous shard is kept, the
    offending chunk and page are named, and the run exits non-zero."""
    source = record(pages=40)
    packed = chunks(source, region(prose(sentences(4), page=57), page=57))

    with pytest.raises(PageRangeError) as raised:
        check_pages(source, packed)

    assert "57" in str(raised.value)
    assert packed[0].passage.passage_id in str(raised.value)


def test_a_chunk_on_the_last_page_passes() -> None:
    """The range is inclusive at both ends: the last page of a source is a legal page."""
    source = record(pages=40)

    check_pages(source, chunks(source, region(prose(sentences(4), page=40), page=40)))


def test_the_page_check_is_skipped_entirely_for_a_pageless_source() -> None:
    """12.8: a pageless source records no page and SHALL NOT be rejected, flagged or delayed
    by this check."""
    source = authored_record()
    packed = chunks(source, entry(Unit(text=sentences(4))))

    check_pages(source, packed)

    assert all(chunk.passage.page_start is None for chunk in packed)


def test_a_pageless_source_synthesises_no_page_or_section_number() -> None:
    """12.8 on the emission side: no page number, no page range, no section number, and none
    invented in place of one."""
    packed = chunks(authored_record(), entry(Unit(text=sentences(4))))

    for chunk in packed:
        assert chunk.passage.section_number is None
        assert chunk.passage.page_start is None
        assert chunk.passage.page_end is None
