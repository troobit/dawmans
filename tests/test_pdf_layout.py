"""Rows, columns and tables — requirements 7.1-7.3 and 7.6, stage 7's geometry half.

Extraction hands over blocks in the order the PDF's content stream drew them, which is
neither reading order nor row order: on Nitro Max p25 the two heading panels arrive before
the word they belong under, and on a Live procedure page the step enumerators arrive after
the step text. Every table fact this spec promises therefore has to be recovered from
bounding boxes, and the acceptance fixture is unforgiving about it.

`nitro_max_p25` is that fixture (7.6). Two side-by-side panels of unequal length — 11 rows
left, 8 right — under a heading printed across three physical lines. A cell belongs to the
trigger printed beside it, not to the cell that happens to share its index in a shorter row,
and the page is never de-interleaved into per-panel runs: 7.2 gives row integrity precedence
precisely because splitting the panels apart destroys the pairings the printed row carries.
"""

from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st

from conftest import FIXTURE_DIR
from dawmans.corpus.pdf.extract import Document, Page
from dawmans.corpus.pdf.layout import (
    CELL_JOIN,
    PANEL_JOIN,
    Prose,
    Table,
    column_positions,
    place,
    rows_of,
    segments,
)
from spanmodel import WIDTH, block_of, page_of, text_line

#: The 19 pairings printed on Nitro Max p25, left panel then right, in printed row order.
PRINTED_PAIRS = {
    "Kick": "36",
    "Snare": "38",
    "Snare Rim": "40",
    "Tom 1": "48",
    "Tom 1 Rim": "50",
    "Tom 2": "45",
    "Tom 2 Rim": "47",
    "Tom 3": "43",
    "Tom 3 Rim": "58",
    "Tom 4": "41",
    "Tom 4 Rim": "39",
    "Ride": "51",
    "Crash 1": "49",
    "Crash 2": "57",
    "Hi-Hat Open": "46",
    "Hi-Hat Half-Open": "23",
    "Hi-Hat Closed": "42",
    "Hi-Hat Pedal": "44",
    "HH Splash": "21",
}

NITRO_HEADING = "Trigger | MIDI Note Number | Trigger | MIDI Note Number"


def fixture(name: str) -> Document:
    raw = (FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")
    return Document.from_dict(json.loads(raw))


def nitro_table() -> Table:
    """The one table on Nitro Max p25."""
    page = fixture("nitro_max_p25").pages[0]
    tables = [segment for segment in segments(page) if isinstance(segment, Table)]
    assert len(tables) == 1, [type(segment).__name__ for segment in segments(page)]
    return tables[0]


def grid(*rows: dict[int, str], top: float = 100.0, leading: float = 20.0) -> Page:
    """A page of cells at fixed column positions, each row a `{column: text}` mapping."""
    return page_of(
        1,
        *(
            block_of(
                *(
                    text_line(text, top=top + index * leading, x0=40.0 + column * 80.0, width=50.0)
                    for column, text in sorted(cells.items())
                )
            )
            for index, cells in enumerate(rows)
            if cells
        ),
    )


def cell_map(table: Table) -> list[dict[int, str]]:
    return [{cell.column: cell.text for cell in row.cells} for row in table.rows]


# --- Rows: what shares a printed line ---------------------------------------------------------


def test_lines_within_the_row_tolerance_are_one_row() -> None:
    """Cells of one printed row are not set to the same baseline: on Nitro Max p25 the
    blank spacer between the panels sits 0.35pt below the cells either side of it."""
    lines = [
        text_line("Kick", top=100.0, x0=40.0),
        text_line("36", top=100.35, x0=120.0),
        text_line("Ride", top=99.7, x0=200.0),
    ]

    rows = rows_of(lines)

    assert len(rows) == 1
    assert [line.text for line in rows[0]] == ["Kick", "36", "Ride"]


def test_a_row_is_ordered_by_x_not_by_extraction_order() -> None:
    lines = [
        text_line("51", top=100.0, x0=280.0),
        text_line("Kick", top=100.0, x0=40.0),
        text_line("36", top=100.0, x0=120.0),
    ]

    assert [line.text for line in rows_of(lines)[0]] == ["Kick", "36", "51"]


def test_lines_beyond_the_tolerance_stay_separate_rows() -> None:
    """The three-line heading is the case: `MIDI Note`, `Trigger` and `Number` are 4.8pt
    apart against a median line height of 8.7, and joining them into one row would put two
    cells of the same column in one row and lose one of them."""
    lines = [
        text_line("MIDI Note", top=79.25, x0=104.0, height=8.7),
        text_line("Trigger", top=84.05, x0=31.5, height=8.7),
        text_line("Number", top=88.85, x0=104.0, height=8.7),
    ]

    assert [[line.text for line in row] for row in rows_of(lines)] == [
        ["MIDI Note"],
        ["Trigger"],
        ["Number"],
    ]


def test_blank_lines_are_not_cells() -> None:
    """The spacer column between Nitro Max's panels is a run of blank spans on every row.
    Kept, it becomes a column with an empty heading and breaks the panel repeat."""
    lines = [text_line("Kick", top=100.0, x0=40.0), text_line(" ", top=100.0, x0=120.0)]

    assert [line.text for line in rows_of(lines)[0]] == ["Kick"]


# --- Columns and cells: placed by x, never by index --------------------------------------------


def test_a_cell_is_placed_by_x_position_not_by_index() -> None:
    """A ragged row missing its first cell: by index `39` is the trigger name, by position
    it is the number it is printed under."""
    page = grid({0: "Kick", 1: "36"}, {0: "Snare", 1: "38"}, {1: "39"})
    rows = rows_of(page.lines)
    columns = column_positions(rows, page.width)

    placed = place(rows[2], columns)

    assert [(cell.column, cell.text) for cell in placed.cells] == [(1, "39")]


def test_columns_cluster_within_two_percent_of_the_page_width() -> None:
    """A column's cells are set flush left but not to the point: the tolerance is what
    keeps `28.8` and `31.5` one column rather than two."""
    page = grid({0: "Kick", 1: "36"}, {0: "Snare", 1: "38"})
    for line in page.lines:
        if line.text == "Snare":
            line.bbox = (line.bbox[0] + 0.02 * WIDTH * 0.9, *line.bbox[1:])

    assert len(column_positions(rows_of(page.lines), page.width)) == 2


@given(
    shape=st.lists(
        st.lists(st.booleans(), min_size=1, max_size=4).filter(any),
        min_size=1,
        max_size=8,
    ),
    jitter=st.lists(st.floats(min_value=-2.0, max_value=2.0), min_size=8, max_size=8),
)
def test_recovered_rows_equal_generated_rows(shape: list[list[bool]], jitter: list[float]) -> None:
    """Property — row integrity (design §Property-based tests, 7.1-7.2). Rows are generated
    ragged on purpose: a table whose rows all hold the same cells cannot tell placement by
    position from placement by index, and every panel table in this corpus is ragged."""
    drawn = [
        {column: f"r{row}c{column}" for column, present in enumerate(cells) if present}
        for row, cells in enumerate(shape)
    ]
    # A column index is a position among the columns the page actually uses, so a grid whose
    # left column is empty throughout has no column 0 to recover.
    rank = {column: index for index, column in enumerate(sorted({c for row in drawn for c in row}))}
    generated = [{rank[column]: text for column, text in row.items()} for row in drawn]
    page = page_of(
        1,
        *(
            block_of(
                *(
                    text_line(
                        text,
                        top=100.0 + row * 20.0 + jitter[column % len(jitter)] * 0.5,
                        x0=40.0 + column * 80.0 + jitter[row % len(jitter)],
                        width=50.0,
                    )
                    for column, text in sorted(cells.items())
                )
            )
            for row, cells in enumerate(drawn)
        ),
    )

    rows = rows_of(page.lines)
    columns = column_positions(rows, page.width)
    recovered = [{cell.column: cell.text for cell in place(row, columns).cells} for row in rows]

    assert recovered == generated


# --- Nitro Max p25: the acceptance fixture (7.6) -----------------------------------------------


def test_the_heading_joins_three_physical_lines() -> None:
    """7.3. `MIDI Note` and `Number` are separate printed lines in the same column; the
    naive reading takes the first as a data row and loses the second."""
    assert nitro_table().heading_text == NITRO_HEADING


def test_the_heading_rows_are_not_data_rows() -> None:
    assert len(nitro_table().rows) == 11
    assert "Trigger" not in [cell.text for row in nitro_table().rows for cell in row.cells]


def test_all_nineteen_trigger_to_note_pairs_are_recoverable() -> None:
    """7.6, the acceptance criterion. Every trigger is paired with the number printed
    beside it, across both panels and through the ragged tail."""
    table = nitro_table()
    pairs = {}
    for row in table.rows:
        cells = {cell.column: cell.text for cell in row.cells}
        for trigger, number in ((0, 1), (2, 3)):
            if trigger in cells:
                pairs[cells[trigger]] = cells.get(number)

    assert pairs == PRINTED_PAIRS


def test_the_ragged_rows_carry_only_their_own_panel() -> None:
    """Rows 9-11 are printed in the left panel alone. A reading that pairs the panels by row
    index rather than by x-position grafts a right-hand trigger onto them — the failure 7.6
    names, and the reason the fixture is ragged."""
    tail = cell_map(nitro_table())[8:]

    assert tail == [
        {0: "Tom 3 Rim", 1: "58"},
        {0: "Tom 4", 1: "41"},
        {0: "Tom 4 Rim", 1: "39"},
    ]


def test_panel_boundaries_come_from_the_repeated_heading() -> None:
    """7.6 and design §Panel boundaries: columns 1-2 and 3-4 carry identical joined
    headings, and that repeat is the boundary. No x is hardcoded anywhere."""
    assert nitro_table().panels == (0, 2)


def test_a_table_with_one_panel_has_one_boundary() -> None:
    """The repeat is evidence, so its absence is too: a table whose headings are all
    different is one panel, however many columns it has."""
    page = grid(
        {0: "Trigger", 1: "Note", 2: "Kit"},
        {0: "Kick", 1: "36", 2: "1"},
        {0: "Snare", 1: "38", 2: "2"},
        {0: "Ride", 1: "51", 2: "3"},
    )

    table = next(segment for segment in segments(page) if isinstance(segment, Table))

    assert table.heading == ("Trigger", "Note", "Kit")
    assert table.panels == (0,)


def test_rows_serialise_in_printed_order_with_the_boundary_marked() -> None:
    table = nitro_table()

    assert table.row_text(table.rows[0]) == f"Kick{CELL_JOIN}36{PANEL_JOIN}Ride{CELL_JOIN}51"
    assert table.row_text(table.rows[10]) == f"Tom 4 Rim{CELL_JOIN}39"


def test_the_page_is_never_reordered_into_per_panel_runs() -> None:
    """7.2's precedence rule. De-interleaving the panels reads the whole left column before
    `Ride`, and the printed pairing is unrecoverable from that order."""
    order = [cell.text for row in nitro_table().rows for cell in row.cells]

    assert order[:4] == ["Kick", "36", "Ride", "51"]
    assert order.index("Ride") < order.index("Snare")


def test_a_tabular_region_is_not_column_segmented() -> None:
    """Design step 5: tabular content orders by (row, x) and column segmentation is not
    applied to it. The page has four full-height columns, so reading it as prose would order
    all eleven triggers before any note number."""
    page = fixture("nitro_max_p25").pages[0]

    loose = [
        line.text.strip()
        for segment in segments(page)
        if isinstance(segment, Prose)
        for line in segment.lines
    ]

    assert loose == ["(5.2) Pad MIDI Note Numbers", "25"]


# --- Prose: the other half of 7.2 --------------------------------------------------------------


def two_column_prose() -> Page:
    """A page set in two full-height columns, extracted in row order — which is how a
    two-column page reads back as alternating half-sentences."""
    left = [
        "Session View is where clips are launched",
        "and recorded, one column to a track.",
        "Arrangement View lays the same clips out",
    ]
    right = [
        "against time, and the two views hold the",
        "same Set. Recording in one is audible in",
        "the other without any further step.",
    ]
    return page_of(
        1,
        *(
            block_of(
                *(
                    text_line(text, top=100.0 + index * 40.0, x0=x0, width=140.0)
                    for x0, text in ((40.0, one), (210.0, other))
                )
            )
            for index, (one, other) in enumerate(zip(left, right, strict=True))
        ),
    )


def test_prose_with_two_full_height_columns_orders_by_column_then_y() -> None:
    page = two_column_prose()

    prose = [segment for segment in segments(page) if isinstance(segment, Prose)]

    assert len(prose) == 1
    assert [line.text for line in prose[0].lines] == [
        "Session View is where clips are launched",
        "and recorded, one column to a track.",
        "Arrangement View lays the same clips out",
        "against time, and the two views hold the",
        "same Set. Recording in one is audible in",
        "the other without any further step.",
    ]


def test_single_column_prose_stays_in_reading_order() -> None:
    page = page_of(
        1,
        block_of(
            text_line("A Project is created whenever you save a Live Set.", top=100.0),
            text_line("Presets can be saved into the current Project.", top=120.0),
        ),
    )

    prose = next(segment for segment in segments(page) if isinstance(segment, Prose))

    assert [line.text for line in prose.lines] == [
        "A Project is created whenever you save a Live Set.",
        "Presets can be saved into the current Project.",
    ]


def test_a_page_of_prose_and_a_table_yields_both_in_printed_order() -> None:
    """Segments come back in printed order, so the section title still precedes its table
    and the page number still trails it — stage 7 drops the latter, and cannot if the
    ordering has already been lost."""
    page = fixture("furniture_pages").pages[2]

    kinds = [type(segment).__name__ for segment in segments(page)]

    assert kinds == ["Prose", "Table", "Prose"]
