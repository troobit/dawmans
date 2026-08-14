"""Unit assembly and the furniture drop — stage 7, requirements 3.5, 3.6, 7.4, 7.5, 10.3.

Stage 7 is where the annotated span model becomes the shared `Region`/`Unit` shape that the
chunker and `data/symptom-triage` both consume, and it is the last stage that can discard
anything. The mark-then-clear ordering ends here: stage 3 marked the running headers and
page numbers without being able to see a section anchor or a table, stage 5 cleared the mark
on the lines an anchor resolved to, this stage clears it inside a detected table, and what
is still marked is dropped. Text is discarded once and by one stage.

The atomic flags are the other half. 6.10 and 7.4 forbid splitting a numbered procedure or a
table row that fits the cap, and 7.5 makes the joined heading a `repeat_on_split` unit so a
split table's second chunk still says what its columns mean. Both are decided here, on
geometry the chunker no longer has.
"""

from __future__ import annotations

import json
from collections import Counter

from conftest import FIXTURE_DIR
from dawmans.corpus.loader import Region
from dawmans.corpus.pdf.extract import Document
from dawmans.corpus.pdf.furniture import mark_furniture
from dawmans.corpus.pdf.layout import CELL_JOIN, PANEL_JOIN
from dawmans.corpus.pdf.sections import section_map
from dawmans.corpus.pdf.units import FIGURE_AREA, assemble, has_figures
from spanmodel import HEIGHT, WIDTH, block_of, document_of, footer, page_of, text_line


def fixture(name: str) -> Document:
    raw = (FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")
    return Document.from_dict(json.loads(raw))


def loaded(name: str) -> tuple[Document, tuple[Region, ...]]:
    """A fixture through stages 3, 5 and 7 — the order the load path runs them in."""
    document = fixture(name)
    mark_furniture(document)
    return document, assemble(document, section_map(document))


def texts(regions: tuple[Region, ...]) -> list[str]:
    return [unit.text for region in regions for unit in region.units]


def words(text: str) -> list[str]:
    """A unit's words, without the separators serialisation adds."""
    return text.replace(PANEL_JOIN, " ").replace(CELL_JOIN, " ").split()


def table_grid(*rows: list[str], top: float = 100.0) -> list:
    return [
        block_of(
            *(
                text_line(text, top=top + index * 20.0, x0=40.0 + column * 80.0, width=50.0)
                for column, text in enumerate(cells)
            )
        )
        for index, cells in enumerate(rows)
    ]


# --- Tables: a row is atomic, the heading repeats on split -------------------------------------


def test_a_table_row_is_one_atomic_unit() -> None:
    """7.4: a row that fits the cap is never split, so it reaches the chunker as one unit
    with its cells in printed order and its panel boundary marked."""
    _, regions = loaded("nitro_max_p25")
    units = [unit for region in regions for unit in region.units]

    row = next(unit for unit in units if unit.text.startswith("Kick"))

    assert row.text == f"Kick{CELL_JOIN}36{PANEL_JOIN}Ride{CELL_JOIN}51"
    assert row.atomic
    assert not row.repeat_on_split


def test_the_joined_heading_is_emitted_repeat_on_split() -> None:
    """7.5: a table over the cap splits between rows and every part carries the heading, so
    the heading is a unit of its own rather than a line of the first row."""
    _, regions = loaded("nitro_max_p25")

    heading = next(
        unit for region in regions for unit in region.units if unit.text.startswith("Trigger")
    )

    assert heading.text == "Trigger | MIDI Note Number | Trigger | MIDI Note Number"
    assert heading.repeat_on_split
    assert heading.atomic


def test_the_ragged_rows_keep_their_own_pairing() -> None:
    _, regions = loaded("nitro_max_p25")

    assert f"Tom 4 Rim{CELL_JOIN}39" in texts(regions)


# --- Procedures: 3.5 and 6.10 ------------------------------------------------------------------


def test_a_numbered_procedure_is_one_atomic_unit() -> None:
    """6.10. The enumerators are set in a left gutter and extract after the step text, so
    only row assembly on geometry puts `1.` back in front of its step."""
    _, regions = loaded("live_procedure_pagebreak")

    procedure = next(
        unit for region in regions for unit in region.units if unit.text.startswith("1.")
    )

    starts = [line.split(maxsplit=1)[0] for line in procedure.text.splitlines() if line]

    assert procedure.atomic
    assert [start for start in starts if start.rstrip(".").isdigit()] == [
        "1.",
        "2.",
        "3.",
        "4.",
        "5.",
    ]


def test_a_unit_spanning_a_page_break_keeps_both_ends() -> None:
    """6.8 and 6.10 together: steps 1-4 are on p158 and step 5 on p159, and the unit that
    holds them records both pages. One page per unit would force either a 6.10 violation or
    a citation naming p158 for text printed on p159."""
    _, regions = loaded("live_procedure_pagebreak")

    procedure = next(
        unit for region in regions for unit in region.units if unit.text.startswith("1.")
    )

    assert (procedure.page_start, procedure.page_end) == (158, 159)


def test_prose_is_not_atomic() -> None:
    _, regions = loaded("live_procedure_pagebreak")

    paragraph = next(
        unit for region in regions for unit in region.units if unit.text.startswith("A Project")
    )

    assert not paragraph.atomic
    assert (paragraph.page_start, paragraph.page_end) == (158, 158)


# --- The furniture drop (3.6) ------------------------------------------------------------------


def test_the_repeated_page_number_does_not_reach_a_unit() -> None:
    document, regions = loaded("furniture_pages")

    assert {page.number for page in document.pages} == {23, 24, 25, 26}
    for number in ("23", "24", "25", "26"):
        assert number not in texts(regions)


def test_an_in_table_numeric_line_survives_the_drop() -> None:
    """The other half of 3.6: the rule that suppresses a page number must not suppress the
    numbers printed in Nitro Max's kit and note tables, which are the answer to the question
    the manual is indexed for."""
    _, regions = loaded("furniture_pages")

    assert f"Kick{CELL_JOIN}36{PANEL_JOIN}Ride{CELL_JOIN}51" in texts(regions)
    # The kit table on p26 prints no heading, so there is no repeated heading sequence to
    # read a panel boundary from and its four columns serialise as one panel.
    assert CELL_JOIN.join(["1", "Deep Rock", "17", "Room"]) in texts(regions)


def test_the_furniture_mark_is_cleared_inside_a_detected_table() -> None:
    """Stage 7's half of mark-then-clear. A table row printed low enough to fall in the
    footer band is marked by stage 3, which cannot see the table; this stage can, and the
    row is table content whatever band it sits in."""
    page = page_of(1, *table_grid(["Trigger", "Note", "Kit"], ["Kick", "36", "1"]))
    page.blocks.extend(table_grid(["Snare", "38", "2"], ["Ride", "51", "3"], top=HEIGHT * 0.95))
    document = document_of(page)
    for line in page.lines:
        if line.text in ("Ride", "51", "3"):
            line.furniture = True

    regions = assemble(document, section_map(document))

    assert f"Ride{CELL_JOIN}51{CELL_JOIN}3" in texts(regions)
    assert not any(line.furniture for line in page.lines)


def test_every_surviving_line_reaches_exactly_one_unit() -> None:
    """`Text is discarded once` (design §Stages). A line is dropped as furniture or it
    reaches exactly one unit — never both, and never two units."""
    document, regions = loaded("furniture_pages")

    kept = Counter(
        word
        for page in document.pages
        for block in page.blocks
        if block.english
        for line in block.lines
        if not line.furniture
        for word in line.text.split()
    )

    assert Counter(word for text in texts(regions) for word in words(text)) == kept


def test_a_printed_contents_page_contributes_no_units() -> None:
    """A dot-leader page is structure, not content: indexing it returns a page of section
    titles for every query that matches one. It stays in `page_count` and in the 4.4 audit."""
    document, regions = loaded("live_contents_p13")

    assert document.page_count == 1009
    assert texts(regions) == []


def test_a_non_english_block_contributes_no_units() -> None:
    """4.1, applied where the text is finally assembled. Language selection marks blocks;
    this stage is what stops an unmarked one reaching the index."""
    spanish = block_of(text_line("Mantenga pulsado el botón de encendido.", top=200.0))
    spanish.english = False
    document = document_of(
        page_of(1, block_of(text_line("Hold the power button to switch on.", top=100.0)), spanish)
    )

    regions = assemble(document, section_map(document))

    assert texts(regions) == ["Hold the power button to switch on."]


# --- Figures (10.3) ----------------------------------------------------------------------------


def test_has_figures_needs_a_placed_area_over_the_threshold() -> None:
    """10.3 via design §Figures: `get_images()` returns every XObject including logos, rules
    and background panels, so on a screenshot-dense manual an unfiltered flag sets almost
    everywhere and stops discriminating."""
    page = page_of(1, block_of(text_line("Velocity curves.", top=100.0)))
    page.images = [(0.0, 0.0, WIDTH * 0.05, HEIGHT * 0.05)]

    assert not has_figures(page)

    page.images = [(0.0, 0.0, WIDTH * 0.5, HEIGHT * 0.5)]

    assert has_figures(page)


def test_the_threshold_is_two_percent_of_the_page() -> None:
    page = page_of(1, block_of(text_line("Velocity curves.", top=100.0)))
    side = (FIGURE_AREA * WIDTH * HEIGHT) ** 0.5

    page.images = [(0.0, 0.0, side * 0.99, side)]
    assert not has_figures(page)

    page.images = [(0.0, 0.0, side * 1.01, side)]
    assert has_figures(page)


def test_only_units_on_a_page_carrying_a_figure_are_flagged() -> None:
    """Six velocity-curve plots are printed on p24 and nowhere else in the fixture."""
    _, regions = loaded("furniture_pages")
    units = [unit for region in regions for unit in region.units]

    flagged = {page for unit in units if unit.flags.has_figures for page in (unit.page_start,)}

    assert flagged == {24}


# --- Order (data/symptom-triage 1.5) -----------------------------------------------------------


def test_units_are_in_printed_order() -> None:
    """`Region.units` is ordered and no stage reorders them — `data/symptom-triage` 1.5
    depends on it, and so does every citation that quotes a procedure."""
    _, regions = loaded("nitro_max_p25")

    assert texts(regions)[:3] == [
        "(5.2) Pad MIDI Note Numbers",
        "Trigger | MIDI Note Number | Trigger | MIDI Note Number",
        f"Kick{CELL_JOIN}36{PANEL_JOIN}Ride{CELL_JOIN}51",
    ]


def test_a_regions_page_range_covers_its_own_units() -> None:
    """6.8 at region granularity: the range is what the region's surviving text occupies,
    not the span of lines its anchor happened to reach over."""
    _, regions = loaded("furniture_pages")

    for region in regions:
        pages = [unit.page_start for unit in region.units] + [
            unit.page_end for unit in region.units
        ]
        if pages:
            assert (region.page_start, region.page_end) == (min(pages), max(pages))


def test_a_page_with_a_footer_only_yields_no_units() -> None:
    """A page whose one line is a running footer contributes nothing, and does not fail."""
    document = document_of(
        page_of(1, footer("1"), block_of(text_line("Setting up the drum module.", top=100.0))),
        page_of(2, footer("2")),
    )
    mark_furniture(document)

    regions = assemble(document, section_map(document))

    assert texts(regions) == ["Setting up the drum module."]
