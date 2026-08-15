"""The section map — requirements 6.3-6.6, stage 5.

Three sources of structure, tried in order: the embedded outline, a printed contents page,
and heading styles. All three are content-side, and none of them is per-manual
configuration (6.6) — that is the point of trying three rather than declaring one.

**Path C's quality gate is the dangerous one.** "A style larger than the body" is met by
almost any PDF, a cover title alone clears it, and path C firing wrongly is worse than path
C not firing at all: a title plus a strapline yields two regions spanning the whole
document, and every citation inside them names a wrong section. 6.4 and 6.5 already say
what to do when structure cannot be found — one titled region, citations without a section
number — so the gate is written to fail closed, and `cover_only` is the fixture that pins
it.

The corpus check of design §Section map applies throughout: every manual in this corpus
carries an embedded outline, so paths B and C have no live instance. Their fixtures are
captured with the outline withheld, and the gate's own rules are asserted against hand-built
span models where the counts are the thing under test.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from conftest import FIXTURE_DIR
from dawmans.corpus.pdf.extract import Document, TocEntry
from dawmans.corpus.pdf.furniture import mark_furniture
from dawmans.corpus.pdf.sections import (
    HEADING_MIN_COUNT,
    NUMBERED_RATIO,
    PATH_CONTENTS,
    PATH_HEADINGS,
    PATH_NONE,
    PATH_OUTLINE,
    body_style,
    contents_pages,
    heading_style,
    is_contents_page,
    parse_section_number,
    render_section,
    section_map,
)
from spanmodel import HEIGHT, WIDTH, block_of, document_of, footer, page_of, span, text_line

HEADING_FONT = "futura-pt-Ultra-Bold-40"


def fixture(name: str) -> Document:
    raw = (FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")
    return Document.from_dict(json.loads(raw))


def headed_pages(count: int, headings: dict[int, str], *, size: float = 15.0) -> Document:
    """`count` pages of body text, with a heading in a larger style on the named pages."""
    return document_of(
        *(
            page_of(
                number,
                *(
                    [block_of(text_line(headings[number], top=60.0, font=HEADING_FONT, size=size))]
                    if number in headings
                    else []
                ),
                block_of(
                    text_line(
                        "The Session View is where clips are launched and recorded live.",
                        top=100.0,
                    ),
                    text_line("Each column of the grid is one track of the Set.", top=113.2),
                ),
            )
            for number in range(1, count + 1)
        )
    )


# --- The section number: parsed off both printed forms ------------------------------------


@pytest.mark.parametrize(
    ("printed", "number", "title"),
    [
        ("24.1 An Overview of Racks", "24.1", "An Overview of Racks"),
        ("(1.3.1) Connection Diagram", "1.3.1", "Connection Diagram"),
        ("(5.2) Pad MIDI Note Numbers", "5.2", "Pad MIDI Note Numbers"),
        ("24. Instrument, Drum and Effect Racks", "24", "Instrument, Drum and Effect Racks"),
        ("28.21.1.1 Context Menu Options", "28.21.1.1", "Context Menu Options"),
        ("Introduction", None, "Introduction"),
        ("Box Contents", None, "Box Contents"),
        ("8x5 matrix of Clip Buttons", None, "8x5 matrix of Clip Buttons"),
    ],
)
def test_the_number_is_parsed_off_the_printed_title(
    printed: str, number: str | None, title: str
) -> None:
    """Live prints `24.1 Title` and the Nitro Max prints `(1.3.1) Title`. The number comes
    off the title because the citation renders it separately — leaving it in would render
    `§24.1 24.1 An Overview of Racks`."""
    assert parse_section_number(printed) == (number, title)


@given(
    parts=st.lists(st.integers(min_value=1, max_value=99), min_size=1, max_size=4),
    title=st.text(alphabet=st.characters(categories=("Lu", "Ll")), min_size=1, max_size=40),
    parenthesised=st.booleans(),
)
def test_section_number_round_trip(parts: list[int], title: str, parenthesised: bool) -> None:
    """Property — section-number round-trip (design §Property-based tests): `parse(render())`
    is the identity across both printed forms. A number that survives the trip is one a
    citation can be rendered from."""
    number = ".".join(str(part) for part in parts)
    printed = render_section(number, title)
    if parenthesised:
        printed = f"({number}) {title}"

    assert parse_section_number(printed) == (number, title)


# --- Path A: the embedded outline ----------------------------------------------------------


def test_an_outline_of_two_entries_is_path_a() -> None:
    document = headed_pages(4, {})
    document.toc = [TocEntry(1, "1 Getting Started", 1), TocEntry(1, "2 Recording", 3)]

    mapping = section_map(document)

    assert mapping.path == PATH_OUTLINE
    assert [entry.title for entry in mapping.entries] == ["Getting Started", "Recording"]
    assert not mapping.inferred


def test_an_outline_of_one_entry_is_not_enough_for_path_a() -> None:
    """`doc.get_toc()` returns >=2 entries (design §Section map). One entry is a PDF
    carrying a link to its own cover, which is not a structure."""
    document = headed_pages(4, {})
    document.toc = [TocEntry(1, "Cover", 1)]

    assert section_map(document).path != PATH_OUTLINE


def test_the_parent_chain_comes_off_the_outline_levels() -> None:
    """`Sidechain Parameters` occurs eight times in Live's TOC, so the leaf title alone does
    not identify a section. The nearest two ancestors are kept, outermost first."""
    document = headed_pages(4, {})
    document.toc = [
        TocEntry(1, "28. Live Audio Effect Reference", 1),
        TocEntry(2, "28.21 Glue Compressor", 2),
        TocEntry(3, "28.21.1 Sidechain Parameters", 3),
        TocEntry(4, "28.21.1.1 Context Menu Options", 4),
    ]

    entries = section_map(document).entries

    assert entries[2].path == ("Live Audio Effect Reference", "Glue Compressor")
    assert entries[3].path == ("Glue Compressor", "Sidechain Parameters")
    assert entries[0].path == ()


def test_live_toc_slice_takes_path_a() -> None:
    document = fixture("live_toc_slice")
    mapping = section_map(document)

    assert mapping.path == PATH_OUTLINE
    assert mapping.numbered
    assert [entry.number for entry in mapping.entries][:3] == ["24", "24.1", "24.1.1"]


# --- Path B: the printed contents page -----------------------------------------------------


def contents_document(page_count: int = 20) -> Document:
    """A Nitro-Max-shaped contents page: `(1.3.1) Connection Diagram ...... 5`."""
    printed = [
        "(1.0) Introduction .................. 3",
        "(1.1) Box Contents .................. 3",
        "(1.2) Support ....................... 4",
        "(1.3) Setup ......................... 5",
        "(1.3.1) Connection Diagram .......... 5",
        "(2.0) Features ...................... 7",
    ]
    return document_of(
        page_of(
            1,
            block_of(
                *(text_line(line, top=100.0 + index * 13.2) for index, line in enumerate(printed))
            ),
        ),
        *(page_of(number) for number in range(2, page_count + 1)),
        page_count=page_count,
    )


def test_a_dot_leader_page_is_path_b_when_there_is_no_outline() -> None:
    mapping = section_map(contents_document())

    assert mapping.path == PATH_CONTENTS
    assert [(entry.number, entry.title, entry.page) for entry in mapping.entries][:2] == [
        ("1.0", "Introduction", 3),
        ("1.1", "Box Contents", 3),
    ]


def test_path_b_nests_by_the_depth_of_the_parsed_number() -> None:
    """There are no levels on a printed page, so the number supplies them: `(1.3.1)` sits
    under `(1.3)`, and the parent chain that stops a duplicate title being ambiguous comes
    out of the same rule as path A's. `(1.0)` and `(1.3)` are the same depth and therefore
    the same level, so `Setup` is the only ancestor this page can support — path A reads
    the level off the outline and does better."""
    entries = section_map(contents_document()).entries
    connection = next(entry for entry in entries if entry.title == "Connection Diagram")

    assert connection.level == 3
    assert connection.path == ("Setup",)


def test_path_b_takes_the_number_group_as_optional() -> None:
    """Design §Section map: `with the number group optional`. A contents page with no
    numbering is still a contents page, and its document is unnumbered under 6.4."""
    document = document_of(
        page_of(
            1,
            block_of(
                *(
                    text_line(f"{title} ......... {page}", top=100.0 + index * 13.2)
                    for index, (title, page) in enumerate(
                        [
                            ("Introduction", 3),
                            ("Box Contents", 3),
                            ("Support", 4),
                            ("Setup", 5),
                            ("Features", 7),
                        ]
                    )
                )
            ),
        ),
        *(page_of(number) for number in range(2, 11)),
    )

    mapping = section_map(document)

    assert mapping.path == PATH_CONTENTS
    assert not mapping.numbered
    assert all(entry.number is None for entry in mapping.entries)


# --- Printed contents pages are excluded from chunking, on every document -------------------


def test_live_contents_p13_is_a_contents_page_without_dot_leaders() -> None:
    """Live sets its contents page numbers as a right-hand column of bare numerals, so the
    dot-leader grammar does not match them (design §Section map, corpus check). The
    exclusion cannot rest on that grammar alone or Live's 12 contents chunks reach the
    index — and they BM25-match every verbatim section title in the document."""
    document = fixture("live_contents_p13")
    mark_furniture(document)

    assert contents_pages(document) == frozenset({13})


def test_a_contents_page_is_excluded_even_when_the_outline_supplied_the_structure() -> None:
    """`applied to every page of every document, not only when path B is chosen`. Live takes
    path A and still prints pp2-21 of contents."""
    document = fixture("live_contents_p13")
    document.toc = [TocEntry(1, "28.17 Erosion", 13), TocEntry(1, "28.18 External Audio", 13)]

    mapping = section_map(document)

    assert mapping.path == PATH_OUTLINE
    assert mapping.contents_pages == frozenset({13})


def test_a_table_of_numbers_is_not_a_contents_page() -> None:
    """The MIDI note table is a page of short titles beside bare numerals, which is what a
    contents page looks like from a distance. Two things separate them: the numerals sit in
    the body of the page rather than in a right-hand band, and 36-58 are not page numbers of
    a 35-page guide."""
    document = fixture("nitro_max_p25")
    mark_furniture(document)

    assert contents_pages(document) == frozenset()


def test_a_prose_page_is_not_a_contents_page() -> None:
    document = fixture("live_toc_slice")
    mark_furniture(document)

    assert contents_pages(document) == frozenset()


def test_a_short_page_of_numerals_is_not_a_contents_page() -> None:
    """A minimum entry count, because three lines that happen to end in a numeral are not a
    table of contents and suppressing them loses real text silently."""
    document = document_of(
        page_of(
            1,
            block_of(text_line("Appendix A", top=100.0)),
            block_of(text_line("23", top=100.0, x0=WIDTH * 0.9, width=12.0)),
        )
    )

    assert not is_contents_page(document.pages[0], document.page_count)


# --- Path C: heading styles, and the gate that keeps it shut -------------------------------


def test_cover_only_fails_the_gate() -> None:
    """A title plus a strapline in two large styles, on one page of a 1009-page manual.
    Under a bare `>=2 spans larger than the body` test this yields two regions spanning the
    whole document and every citation in it names a wrong section (6.5)."""
    document = fixture("cover_only")

    mapping = section_map(document)

    assert heading_style(document) is None
    assert mapping.path == PATH_NONE
    assert mapping.entries == ()


def test_a_style_used_across_the_document_qualifies() -> None:
    document = headed_pages(
        10,
        {1: "Getting Started", 4: "Recording", 7: "Mixing", 10: "Exporting"},
    )

    mapping = section_map(document)

    assert mapping.path == PATH_HEADINGS
    assert mapping.inferred
    assert [entry.title for entry in mapping.entries] == [
        "Getting Started",
        "Recording",
        "Mixing",
        "Exporting",
    ]


def test_the_report_records_the_heading_count_and_the_qualifying_style() -> None:
    """Path C is inference and the report is where that is visible; a wrong style shows up
    as a count that does not match the document."""
    mapping = section_map(headed_pages(10, {1: "One", 4: "Two", 7: "Three", 10: "Four"}))

    assert mapping.heading_count == 4
    assert mapping.heading_style == (HEADING_FONT, 15.0)


def test_three_headings_are_not_enough() -> None:
    document = headed_pages(10, {1: "One", 5: "Two", 10: "Three"})

    assert heading_style(document) is None
    assert HEADING_MIN_COUNT == 4


def test_headings_clustered_at_the_front_fail_the_spread() -> None:
    """Four large lines on the first page of a long document is a cover, not a structure."""
    document = headed_pages(20, {})
    for index, title in enumerate(["One", "Two", "Three", "Four"]):
        document.pages[0].blocks.insert(
            index,
            block_of(text_line(title, top=60.0 + index * 20.0, font=HEADING_FONT, size=15.0)),
        )

    assert heading_style(document) is None


def test_a_style_below_one_heading_per_ten_pages_fails_the_rate() -> None:
    document = headed_pages(60, {1: "One", 20: "Two", 40: "Three", 60: "Four"})

    assert heading_style(document) is None


def test_a_line_ending_in_a_full_stop_is_not_a_heading() -> None:
    """A pull quote set large is a sentence, and a sentence is not a section title."""
    document = headed_pages(
        10,
        {
            1: "Set the input gain.",
            4: "Arm the track.",
            7: "Press record.",
            10: "Stop the transport.",
        },
    )

    assert heading_style(document) is None


def test_a_long_line_is_not_a_heading() -> None:
    """`shorter than 60% of the modal line length`: a paragraph set in a display face runs
    the width of the measure, and a heading does not."""
    long_title = "The Session View is where clips are launched and recorded live in the Set"
    document = headed_pages(10, dict.fromkeys([1, 4, 7, 10], long_title))

    assert heading_style(document) is None


def test_a_style_that_does_not_start_a_line_is_not_a_heading() -> None:
    """A run of large characters mid-line is emphasis inside a sentence. Requiring the span
    to start its line is what separates the two without reading the words."""
    document = headed_pages(10, {})
    for number in (1, 4, 7, 10):
        page = document.pages[number - 1]
        page.blocks[0].lines[0].spans.append(
            span("Session View", font=HEADING_FONT, size=15.0, x0=300.0, top=100.0, width=80.0)
        )

    assert heading_style(document) is None


def test_the_body_style_is_the_one_most_lines_are_set_in() -> None:
    document = headed_pages(10, {1: "One", 4: "Two", 7: "Three", 10: "Four"})

    style = body_style(document)

    assert (style.font, style.size) == ("HelveticaNeue-Roman", 10.0)


# --- Numbering: 6.3 or 6.4, decided by the document ----------------------------------------


def test_a_document_whose_entries_carry_numbers_is_numbered() -> None:
    document = headed_pages(4, {})
    document.toc = [
        TocEntry(1, "1 Getting Started", 1),
        TocEntry(1, "2 Recording", 2),
        TocEntry(1, "3 Mixing", 3),
        TocEntry(1, "Colophon", 4),
    ]

    mapping = section_map(document)

    assert mapping.numbered
    assert [entry.number for entry in mapping.entries] == ["1", "2", "3", None]


def test_a_document_below_the_threshold_invents_no_number() -> None:
    """6.4: `SHALL render the citation without a section number rather than inventing one`.
    One numbered heading in a document of five does not make the document numbered, and
    carrying that one number would render `§1` beside four sections that have none."""
    document = headed_pages(5, {})
    document.toc = [
        TocEntry(1, "1 Getting Started", 1),
        TocEntry(1, "Recording", 2),
        TocEntry(1, "Mixing", 3),
        TocEntry(1, "Exporting", 4),
        TocEntry(1, "Colophon", 5),
    ]

    mapping = section_map(document)

    assert not mapping.numbered
    assert all(entry.number is None for entry in mapping.entries)
    assert 1 / 5 < NUMBERED_RATIO


def test_apc_no_toc_carries_no_section_number() -> None:
    """The APC guide is unnumbered: it prints `Introduction`, `Setup`, `Basic Operation` and
    no numbering at all. 6.4 is what reaches the citation, and it holds whichever path fires
    — which is what this asserts, rather than the path.

    The fixture is pp3-4 with the outline withheld, and on two pages the gate refuses: the
    guide's three `Introduction`-style headings are under the count of four, and the spread
    they would need is the whole slice. That is the gate working. Against all 24 pages the
    same style would clear it; a two-page slice cannot show that, and asserting a path here
    would be asserting the slice."""
    document = fixture("apc_no_toc")
    mark_furniture(document)

    mapping = section_map(document)

    assert not mapping.numbered
    assert all(entry.number is None for entry in mapping.entries)


# --- Nothing found at all -------------------------------------------------------------------


def test_a_document_with_no_structure_takes_no_path() -> None:
    """6.4/6.5 catch this: one titled region, weak citations, which the requirements
    anticipate — rather than confident wrong ones."""
    document = document_of(
        *(
            page_of(number, block_of(text_line("Body text at the body size.", top=100.0)))
            for number in range(1, 6)
        )
    )

    mapping = section_map(document)

    assert mapping.path == PATH_NONE
    assert mapping.entries == ()
    assert not mapping.numbered


def test_furniture_is_not_a_heading() -> None:
    """A running header is repeated large text on every page, which is the shape the gate
    looks for. Stage 3 has already marked it, and stage 5 reads the mark."""
    document = document_of(
        *(
            page_of(
                number,
                footer("Ableton Live 12 Reference Manual", height=HEIGHT),
                block_of(text_line("Body text at the body size.", top=100.0)),
            )
            for number in range(1, 11)
        )
    )
    for page in document.pages:
        page.blocks[0].lines[0].spans[0].size = 15.0
        page.blocks[0].lines[0].spans[0].font = HEADING_FONT
    mark_furniture(document)

    assert heading_style(document) is None
