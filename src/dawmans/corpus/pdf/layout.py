"""Rows, columns and tables from span geometry — requirements 7.1-7.6.

Extraction hands over blocks in content-stream order, which is neither reading order nor
row order, so every table fact this spec promises is recovered from bounding boxes here.
Row-first assembly, per the design: cluster lines into rows by y, cluster their x0 values
into columns, place each cell in the column it is printed under, then classify the run as
tabular or prose.

Two rules carry the weight of 7.6:

- **Cells are placed by x-position, never by index.** Nitro Max p25 prints two panels of
  unequal length — 11 rows left, 8 right — so a row past the eighth holds two cells where
  the rows above hold four. Placing by index puts a left-hand trigger's note number under a
  right-hand trigger and the mis-pairing is invisible in the output.
- **The page is never reordered into per-panel runs.** 7.2 gives row integrity precedence
  over column reading order for exactly this layout: de-interleaving the panels destroys the
  pairing each printed row carries. The panel boundary is *marked* in the serialised row and
  the printed order is kept.

Panel boundaries come from the repeated heading sequence rather than any hardcoded x, which
is what makes them work on the next manual as well as this one.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from statistics import median

from dawmans.corpus.pdf.extract import Line, Page

#: Row clustering tolerance, x the region's median line height. Cells of one printed row
#: are not set to a common baseline — Nitro Max's blank panel spacer sits 0.35pt below the
#: cells either side of it — while its three-line heading is 4.8pt against a median of 8.7.
ROW_TOLERANCE = 0.5

#: Column clustering tolerance, x the page width. Wide enough for the sub-point drift
#: between a column's cells, narrow enough to keep adjacent columns apart.
COLUMN_TOLERANCE = 0.02

#: Design §Layout step 4: tabular is >=3 consecutive rows each occupying >=3 of the same
#: columns with short cells. Below that a page of aligned prose reads as a table.
TABLE_MIN_ROWS = 3
TABLE_MIN_COLUMNS = 3

#: A table cell is short. A paragraph that happens to align with one is not a cell.
CELL_MAX_WORDS = 6

#: Rows either side of a detected run join it on weaker evidence — they are already inside
#: a table — but a single-cell row is a caption or a section title, not a ragged row.
TABLE_EDGE_COLUMNS = 2

#: A prose column is full-height when its lines cover this much of the run's height. Below
#: it the "column" is a gutter of step enumerators, and ordering by column would lift every
#: enumerator out of its step.
FULL_HEIGHT = 0.6

#: How a serialised row separates cells, and how it marks a panel boundary (7.6).
CELL_JOIN = " | "
PANEL_JOIN = " ‖ "

_NUMERIC = re.compile(r"^[-+(]?\d+(?:[.,]\d+)*\)?$")


def is_numeric(text: str) -> bool:
    """A cell that reads as a number — the signal that separates a heading from a data row."""
    return bool(_NUMERIC.match(text.strip()))


def is_short(text: str) -> bool:
    return len(text.split()) <= CELL_MAX_WORDS


def printed(lines: Iterable[Line]) -> list[Line]:
    """Non-blank lines. The spacer between Nitro Max's panels is a blank span on every row;
    kept, it becomes a column with an empty heading and the panel repeat stops matching."""
    return [line for line in lines if line.text.strip()]


def median_height(lines: Sequence[Line]) -> float:
    heights = [line.bbox[3] - line.bbox[1] for line in lines if line.bbox[3] > line.bbox[1]]
    return float(median(heights)) if heights else 0.0


def rows_of(lines: Iterable[Line]) -> tuple[tuple[Line, ...], ...]:
    """The printed rows, top to bottom, each ordered by x0."""
    ordered = sorted(printed(lines), key=lambda line: (line.bbox[1], line.bbox[0]))
    if not ordered:
        return ()

    tolerance = ROW_TOLERANCE * median_height(ordered)
    rows: list[list[Line]] = [[ordered[0]]]
    top = ordered[0].bbox[1]
    for line in ordered[1:]:
        if line.bbox[1] - top > tolerance:
            rows.append([])
            top = line.bbox[1]
        rows[-1].append(line)
    return tuple(tuple(sorted(row, key=lambda line: line.bbox[0])) for row in rows)


def column_positions(rows: Iterable[Sequence[Line]], width: float) -> tuple[float, ...]:
    """The x0 of each column, clustered across every row of the region."""
    edges = sorted(line.bbox[0] for row in rows for line in row)
    if not edges:
        return ()

    tolerance = COLUMN_TOLERANCE * width
    clusters: list[list[float]] = [[edges[0]]]
    for edge in edges[1:]:
        if edge - clusters[-1][0] > tolerance:
            clusters.append([])
        clusters[-1].append(edge)
    return tuple(sum(cluster) / len(cluster) for cluster in clusters)


@dataclass(frozen=True)
class Cell:
    """One column's text in one row."""

    text: str
    column: int
    lines: tuple[Line, ...]

    @property
    def line(self) -> Line:
        return self.lines[0]


@dataclass(frozen=True)
class Row:
    """One printed row, its cells placed in the columns they are printed under."""

    cells: tuple[Cell, ...]
    lines: tuple[Line, ...]

    @property
    def top(self) -> float:
        return min(line.bbox[1] for line in self.lines)

    @property
    def columns(self) -> frozenset[int]:
        return frozenset(cell.column for cell in self.cells)

    @property
    def short(self) -> bool:
        return all(is_short(cell.text) for cell in self.cells)


def place(row: Sequence[Line], columns: Sequence[float]) -> Row:
    """Assign each of a row's lines to the column it is printed under.

    By position, never by index: a ragged row missing its first cell must not slide its
    remaining cells left into columns they were not printed in (7.6).
    """
    grouped: dict[int, list[Line]] = {}
    for line in sorted(row, key=lambda line: line.bbox[0]):
        grouped.setdefault(_nearest(line, columns), []).append(line)

    cells = tuple(
        Cell(
            text=" ".join(line.text.strip() for line in lines),
            column=column,
            lines=tuple(lines),
        )
        for column, lines in sorted(grouped.items())
    )
    return Row(cells=cells, lines=tuple(sorted(row, key=lambda line: line.bbox[0])))


@dataclass(frozen=True)
class Table:
    """A run of rows read as tabular, with its heading joined and its panels marked."""

    columns: tuple[float, ...]
    heading: tuple[str, ...]
    heading_rows: tuple[Row, ...]
    rows: tuple[Row, ...]
    #: The first column of each panel (7.6). `(0,)` is one panel across the whole table.
    panels: tuple[int, ...]

    @property
    def lines(self) -> tuple[Line, ...]:
        return tuple(line for row in self.heading_rows + self.rows for line in row.lines)

    @property
    def heading_text(self) -> str:
        """The joined heading, one cell per column — `Trigger | MIDI Note Number | ...`."""
        return CELL_JOIN.join(self.heading)

    def row_text(self, row: Row) -> str:
        """`Kick | 36 ‖ Ride | 51` — printed order, with the panel boundary marked."""
        parts: list[str] = []
        for cell in row.cells:
            if parts:
                parts.append(PANEL_JOIN if cell.column in self.panels else CELL_JOIN)
            parts.append(cell.text)
        return "".join(parts)


@dataclass(frozen=True)
class Prose:
    """A run of rows read as prose, in reading order.

    `rows` holds one entry per printed line — the gutter enumerator of a numbered step and
    the step's text are one entry, so 3.5's discrete steps survive into the units.
    """

    rows: tuple[tuple[Line, ...], ...]

    @property
    def lines(self) -> tuple[Line, ...]:
        return tuple(line for row in self.rows for line in row)


Segment = Table | Prose


def segments(page: Page, lines: Iterable[Line] | None = None) -> tuple[Segment, ...]:
    """The page's tables and prose runs, in printed order.

    Furniture marks are not consulted: stage 7 clears the mark inside a detected table and
    drops what is still marked afterwards, so the detection has to see every line.
    """
    rows = rows_of(page.lines if lines is None else lines)
    if not rows:
        return ()

    placed = [place(row, column_positions(rows, page.width)) for row in rows]
    found: list[Segment] = []
    start = 0
    for first, last in _table_runs(placed):
        if first > start:
            found.append(_prose(rows[start:first], page.width))
        found.append(_table(rows[first:last], page.width))
        start = last
    if start < len(rows):
        found.append(_prose(rows[start:], page.width))
    return tuple(found)


def _table_runs(rows: Sequence[Row]) -> list[tuple[int, int]]:
    """Half-open index ranges of the rows that read as tabular.

    A run is seeded by `TABLE_MIN_ROWS` consecutive rows occupying `TABLE_MIN_COLUMNS` of
    the same columns, then grown over the neighbouring rows that hold at least two cells —
    which is what takes in the joined heading above the run and the ragged rows below it.
    """
    wide = [len(row.columns) >= TABLE_MIN_COLUMNS and row.short for row in rows]
    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(rows):
        if not wide[index]:
            index += 1
            continue
        stop = index
        while stop < len(rows) and wide[stop]:
            stop += 1
        if stop - index < TABLE_MIN_ROWS:
            index = stop
            continue

        first, last = index, stop
        while first > 0 and _joins(rows[first - 1]) and (not runs or runs[-1][1] <= first - 1):
            first -= 1
        while last < len(rows) and _joins(rows[last]):
            last += 1
        runs.append((first, last))
        index = last
    return runs


def _joins(row: Row) -> bool:
    return len(row.columns) >= TABLE_EDGE_COLUMNS and row.short


def _table(rows: Sequence[Sequence[Line]], width: float) -> Table:
    """Build a table from its own rows: the columns are re-clustered over the run alone, so
    a section title printed above it never drags a column sideways."""
    columns = column_positions(rows, width)
    placed = [place(row, columns) for row in rows]
    split = _heading_count(placed)
    heading = _heading(placed[:split], len(columns))
    return Table(
        columns=columns,
        heading=heading,
        heading_rows=tuple(placed[:split]),
        rows=tuple(placed[split:]),
        panels=_panels(heading),
    )


def _heading_count(rows: Sequence[Row]) -> int:
    """How many rows at the top of the run are heading rows (7.3).

    A heading row holds no numeric cell where the rows below hold numbers, or occupies a
    different set of columns from the majority — `MIDI Note` and `Number` are printed in the
    number columns and `Trigger` in the others, and all three are the heading. The first row
    that matches the data pattern ends it, which is what stops `MIDI Note` being read as a
    data row and `Number` being lost.
    """
    numeric = any(is_numeric(cell.text) for row in rows for cell in row.cells)
    pattern, _ = Counter(tuple(sorted(row.columns)) for row in rows).most_common(1)[0]

    count = 0
    for row in rows:
        if any(is_numeric(cell.text) for cell in row.cells):
            break
        if not numeric and tuple(sorted(row.columns)) == pattern:
            break
        count += 1
    return 0 if count == len(rows) else count


def _heading(rows: Sequence[Row], columns: int) -> tuple[str, ...]:
    """Consecutive heading rows joined per column with a space (7.3)."""
    if not rows:
        return ()
    joined = [
        " ".join(cell.text for row in rows for cell in row.cells if cell.column == column)
        for column in range(columns)
    ]
    return tuple(joined)


def _panels(heading: Sequence[str]) -> tuple[int, ...]:
    """The panel boundaries, from the repeated heading sequence and nothing else (7.6)."""
    for size in range(1, len(heading)):
        if len(heading) % size:
            continue
        if all(heading[index] == heading[index % size] for index in range(len(heading))):
            return tuple(range(0, len(heading), size))
    return (0,)


def _prose(rows: Sequence[Sequence[Line]], width: float) -> Prose:
    """A prose run in reading order, ordered by (column, y) where it is set in >=2
    full-height columns — 7.2, so a sentence from one column is not interleaved with the
    next. Anything else keeps its printed order."""
    columns = column_positions(rows, width)
    order = _column_order(rows, columns)
    if order is None:
        return Prose(rows=tuple(tuple(row) for row in rows))

    grouped: list[tuple[Line, ...]] = []
    for index, row in enumerate(rows):
        by_column: dict[int, list[Line]] = {}
        for line in row:
            by_column.setdefault(_nearest(line, columns), []).append(line)
        grouped.extend(
            ((order.index(column) if column in order else len(order), index), tuple(lines))
            for column, lines in sorted(by_column.items())
        )
    return Prose(rows=tuple(lines for _, lines in sorted(grouped, key=lambda pair: pair[0])))


def _column_order(
    rows: Sequence[Sequence[Line]], columns: Sequence[float]
) -> tuple[int, ...] | None:
    """The full-height columns, or None where the run is not multi-column prose."""
    if len(columns) < 2:
        return None

    lines = [line for row in rows for line in row]
    top = min(line.bbox[1] for line in lines)
    bottom = max(line.bbox[3] for line in lines)
    if bottom <= top:
        return None

    full = []
    for index in range(len(columns)):
        held = [line for line in lines if _nearest(line, columns) == index]
        if not held:
            continue
        height = max(one.bbox[3] for one in held) - min(one.bbox[1] for one in held)
        if height >= FULL_HEIGHT * (bottom - top):
            full.append(index)
    return tuple(full) if len(full) >= 2 else None


def _nearest(line: Line, columns: Sequence[float]) -> int:
    return min(range(len(columns)), key=lambda index: abs(columns[index] - line.bbox[0]))


__all__ = [
    "CELL_JOIN",
    "CELL_MAX_WORDS",
    "COLUMN_TOLERANCE",
    "FULL_HEIGHT",
    "PANEL_JOIN",
    "ROW_TOLERANCE",
    "TABLE_EDGE_COLUMNS",
    "TABLE_MIN_COLUMNS",
    "TABLE_MIN_ROWS",
    "Cell",
    "Prose",
    "Row",
    "Segment",
    "Table",
    "column_positions",
    "is_numeric",
    "is_short",
    "median_height",
    "place",
    "printed",
    "rows_of",
    "segments",
]
