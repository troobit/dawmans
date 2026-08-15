"""TOC anchoring, the parent chain and region derivation — 6.5-6.7, stage 5.

Live averages 1.2 TOC entries per page, so attributing text to a section by page number
alone puts several sections' text under one heading and the citation stops naming where the
words are. Anchoring resolves each entry to the line its heading is printed on, and the
region runs from there to the next anchor — which is why a page shared by two sections
splits between them rather than going to whichever entry claimed the page.

The parent chain is the other half. `Sidechain Parameters` occurs eight times in Live's TOC
and 54 of its titles are duplicated, so a chunk indexed as
`Ableton Live 12 — §28.21.1 Sidechain Parameters` names a section the reader cannot find.
The nearest two ancestors are carried on the region; the leaf stays the passage's own title.

Anchoring is also the stage-5 half of the mark-then-clear ordering: a chapter title printed
inside the header band is both furniture and a heading, and the anchor is what says which.
"""

from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st

from conftest import FIXTURE_DIR
from dawmans.corpus.pdf.extract import Document, TocEntry
from dawmans.corpus.pdf.furniture import mark_furniture
from dawmans.corpus.pdf.sections import (
    ANCHOR_NEARBY,
    ANCHOR_PAGE_ONLY,
    ANCHOR_TITLE,
    FRONT_MATTER,
    anchor_entries,
    derive_regions,
    positions,
    section_map,
)
from spanmodel import HEIGHT, block_of, document_of, header, page_of, text_line

HEADING_FONT = "futura-pt-Ultra-Bold-40"

BODY = "The Session View is where clips are launched and recorded live in the Set."


def fixture(name: str) -> Document:
    raw = (FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")
    return Document.from_dict(json.loads(raw))


def manual(headings: dict[int, list[tuple[float, str]]], pages: int = 6) -> Document:
    """`pages` pages of body text with headings printed at named heights, and a TOC that
    names every one of them at the page it is printed on."""
    document = document_of(
        *(
            page_of(
                number,
                *(
                    block_of(text_line(title, top=top, font=HEADING_FONT, size=15.0))
                    for top, title in headings.get(number, [])
                ),
                block_of(
                    text_line(BODY, top=300.0),
                    text_line("Each column of the grid is one track.", top=313.2),
                ),
            )
            for number in range(1, pages + 1)
        )
    )
    document.toc = [
        TocEntry(1, title, number)
        for number in sorted(headings)
        for _, title in sorted(headings[number])
    ]
    return document


def region_at(document: Document, regions, page: int, top: float):
    """The region a line printed at `top` on physical page `page` belongs to.

    A fixture is a slice, so the page index is looked up rather than assumed: `live_toc_slice`
    holds pp470-473 and pp584-592, and p586 is its seventh page."""
    index = next(index for index, one in enumerate(document.pages) if one.number == page)
    return next(region for region in regions if region.contains((index, top, 62.25)))


# --- Anchoring: where an entry actually starts ---------------------------------------------


def test_an_entry_anchors_to_the_line_its_heading_is_printed_on() -> None:
    document = manual({2: [(60.0, "Recording")], 4: [(60.0, "Mixing")]})

    anchors = anchor_entries(document, section_map(document).entries)

    assert [anchor.quality for anchor in anchors] == [ANCHOR_TITLE, ANCHOR_TITLE]
    assert [anchor.position for anchor in anchors] == [(1, 60.0, 72.0), (3, 60.0, 72.0)]


def test_two_entries_on_one_page_anchor_in_printed_order() -> None:
    """`at or after the previous entry's position on that page`. Without the bound, the
    second entry's scan restarts at the top of the page and can match the first heading's
    line — which is how two sections come to start in the same place."""
    document = manual({2: [(60.0, "Recording"), (200.0, "Recording Tips")]})

    anchors = anchor_entries(document, section_map(document).entries)

    assert [anchor.position[1] for anchor in anchors] == [60.0, 200.0]


def test_an_entry_whose_heading_is_a_page_out_anchors_to_the_neighbouring_page() -> None:
    """Outline destinations and printed contents numbers disagree with the physical page by
    one at a chapter break, so the scan tries the target page either side before giving up."""
    document = manual({3: [(60.0, "Mixing")], 5: [(60.0, "Exporting")]})
    document.toc = [TocEntry(1, "Mixing", 2), TocEntry(1, "Exporting", 5)]

    anchors = anchor_entries(document, section_map(document).entries)

    assert anchors[0].quality == ANCHOR_NEARBY
    assert anchors[0].position == (2, 60.0, 72.0)
    assert anchors[1].quality == ANCHOR_TITLE


def test_an_entry_with_no_printed_heading_anchors_at_the_top_of_its_page() -> None:
    """Recorded as `page-only`, so weak sectioning is visible in the run report rather than
    silently producing a region that starts in the wrong place."""
    document = manual({2: [(60.0, "Recording")]})
    document.toc = [TocEntry(1, "Recording", 2), TocEntry(1, "A Heading Nobody Printed", 4)]

    anchors = anchor_entries(document, section_map(document).entries)

    assert anchors[1].quality == ANCHOR_PAGE_ONLY
    assert anchors[1].position[0] == 3


def test_anchoring_clears_the_furniture_mark_on_the_line_it_resolves_to() -> None:
    """The stage-5 half of mark-then-clear. A chapter title set in the header band repeats
    across the chapter, so stage 3 marks it; it is still the heading the citation names."""
    document = manual({}, pages=6)
    for page in document.pages:
        page.blocks.insert(0, header("Recording", height=HEIGHT))
    document.toc = [TocEntry(1, "Recording", 1), TocEntry(1, "Mixing", 4)]
    mark_furniture(document)
    assert document.pages[0].blocks[0].lines[0].furniture

    anchor_entries(document, section_map(document).entries)

    assert not document.pages[0].blocks[0].lines[0].furniture
    assert document.pages[1].blocks[0].lines[0].furniture  # every other page keeps its mark


# --- Regions: what each anchor owns ---------------------------------------------------------


def test_a_region_runs_from_its_anchor_to_the_next() -> None:
    """The page range is the pages the region's own text is printed on, not the pages its
    line span touches. Recording ends at Mixing's heading, the topmost line of p4, so p4
    carries none of Recording's words — recording it as pp2-4 would send CONTRACTS §3's
    open-at-page to a page holding nothing the citation quotes."""
    document = manual({2: [(60.0, "Recording")], 4: [(60.0, "Mixing")]})

    regions = derive_regions(document, section_map(document))

    assert [region.section_title for region in regions] == [FRONT_MATTER, "Recording", "Mixing"]
    assert [(region.page_start, region.page_end) for region in regions] == [(1, 1), (2, 3), (4, 6)]


def test_pages_before_the_first_anchor_are_a_titled_region() -> None:
    """6.5: a title page or a contents page belongs to no section, and a chunk from it must
    not borrow the title of the section that follows."""
    document = fixture("live_toc_slice")
    mark_furniture(document)

    regions = derive_regions(document, section_map(document))

    assert regions[0].section_title == FRONT_MATTER
    assert regions[0].section_number is None
    assert regions[0].page_start == 470


def test_a_front_matter_run_takes_its_own_printed_title_where_it_has_one() -> None:
    document = manual({3: [(60.0, "Mixing")], 5: [(60.0, "Exporting")]})
    document.pages[0].blocks.insert(
        0, block_of(text_line("Ableton Live 12 Manual", top=40.0, font=HEADING_FONT, size=30.0))
    )

    regions = derive_regions(document, section_map(document))

    assert regions[0].section_title == "Ableton Live 12 Manual"


def test_cover_only_yields_one_titled_region() -> None:
    """The failure this fixture exists to catch: a title plus a strapline clearing a bare
    `>=2 large spans` test and producing two regions that between them span 1009 pages,
    every citation in which names a wrong section."""
    document = fixture("cover_only")

    regions = derive_regions(document, section_map(document))

    assert len(regions) == 1
    assert regions[0].section_title == "Ableton Live 12 Manual"
    assert regions[0].section_number is None
    assert not regions[0].inferred


def test_a_page_shared_by_two_sections_splits_between_them() -> None:
    """Live p586 carries the tail of §28.20 Gate above `28.21 Glue Compressor` at y=226.55
    and the head of §28.21 below it. Page-granular attribution gives the whole page to one
    of them, and every quote from the other half is then cited under the wrong section."""
    document = fixture("live_toc_slice")
    mark_furniture(document)

    regions = derive_regions(document, section_map(document))

    gate = region_at(document, regions, 586, 100.0)
    glue = region_at(document, regions, 586, 400.0)
    assert gate.section_title == "Gate"
    assert gate.section_number == "28.20"
    assert (gate.page_start, gate.page_end) == (584, 586)
    assert glue.section_title == "Glue Compressor"
    assert glue.page_start == 586


def test_the_parent_chain_reaches_the_region() -> None:
    """§28.21.1 is one of eight `Sidechain Parameters` in Live's TOC. The device name is on
    the region; the leaf title is what the passage carries, so the citation renders
    `§28.21.1 Glue Compressor › Sidechain Parameters` without the passage duplicating it."""
    document = fixture("live_toc_slice")
    mark_furniture(document)

    regions = derive_regions(document, section_map(document))
    sidechain = next(region for region in regions if region.section_number == "28.21.1")

    assert sidechain.section_title == "Sidechain Parameters"
    assert "Glue Compressor" in sidechain.section_path


def test_a_region_from_the_heading_path_is_marked_inferred() -> None:
    """`inferred` is how a reader tells a section the document declared from one this stage
    guessed at, and path C is the only guessing there is."""
    document = manual(
        {1: [(60.0, "One")], 3: [(60.0, "Two")], 5: [(60.0, "Three")], 6: [(60.0, "Four")]}
    )
    document.toc = []

    regions = derive_regions(document, section_map(document))

    assert all(region.inferred for region in regions)


# --- The property: what the regions have to cover ---------------------------------------------


@given(
    anchors=st.lists(
        st.tuples(st.integers(min_value=1, max_value=6), st.sampled_from([60.0, 150.0, 220.0])),
        min_size=0,
        max_size=6,
        unique=True,
    )
)
def test_regions_are_ordered_non_overlapping_and_cover_every_line(
    anchors: list[tuple[int, float]],
) -> None:
    """Property — TOC cover (design §Property-based tests). Stated over lines rather than
    pages, because a page shared by two sections is the case anchoring exists for: what must
    not overlap is the text, and every line has to reach exactly one region or a chunk of it
    is silently unindexed."""
    headings: dict[int, list[tuple[float, str]]] = {}
    for index, (page, top) in enumerate(sorted(anchors)):
        headings.setdefault(page, []).append((top, f"Heading {index}"))
    document = manual(headings)

    regions = derive_regions(document, section_map(document))

    assert regions
    for earlier, later in zip(regions, regions[1:], strict=False):
        assert earlier.end == later.start

    for position, _line, _page in positions(document):
        covering = [region for region in regions if region.contains(position)]
        assert len(covering) == 1, position


def test_every_page_reaches_at_least_one_region() -> None:
    document = fixture("live_toc_slice")
    mark_furniture(document)

    regions = derive_regions(document, section_map(document))

    covered = {page for region in regions for page in range(region.page_start, region.page_end + 1)}
    assert {page.number for page in document.pages} <= covered
