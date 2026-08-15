"""The annotated span model into `Region[]` — stage 7.

This is the last stage that can discard anything, and the one that ends the mark-then-clear
ordering the design names. Stage 3 marked running headers and page numbers without being
able to see a section anchor or a table; stage 5 cleared the mark on the lines an anchor
resolved to; this stage clears it inside a detected table — a numeric line in Nitro Max's
note table is the answer the manual is indexed for, not a page number — and drops what is
still marked afterwards. Text is discarded once.

The atomic flags are decided here because they are geometry, and the chunker no longer has
any. A table row and a numbered procedure are `atomic` (6.10, 7.4); the joined column
heading is `repeat_on_split` so a split table's later chunks still say what the columns mean
(7.5). A procedure that runs over a page break stays one unit carrying both page numbers,
which is why `Unit` has two page fields rather than one.

Printed contents pages contribute nothing: a dot-leader page is structure, and indexing it
answers every query that matches a section title with a page of section titles. It stays in
`page_count` and in the 4.4 audit.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import groupby

from dawmans.corpus.loader import Region, Unit, UnitFlags
from dawmans.corpus.pdf.extract import Document, Line, Page
from dawmans.corpus.pdf.layout import Prose, Segment, Table, segments
from dawmans.corpus.pdf.sections import RegionSpan, SectionMap, derive_regions, positions

#: 10.3 via design §Figures: an image counts as a figure only when its placed area is this
#: fraction of the page. `get_images()` returns every XObject — logos, rules, background
#: panels — so unfiltered the flag sets almost everywhere on a screenshot-dense manual and
#: stops discriminating.
FIGURE_AREA = 0.02

#: How far left of the first step's text a continuation line may start and still be part of
#: that step. A step's wrapped lines are set to the same indent; the next paragraph is not.
INDENT_TOLERANCE = 1.0

_ENUMERATOR = re.compile(r"^(?P<step>\d+)[.)](?:\s|$)")


def has_figures(page: Page) -> bool:
    """Whether a figure large enough to be worth citing is placed on this page (10.3)."""
    if page.area <= 0:
        return False
    return any(
        (rect[2] - rect[0]) * (rect[3] - rect[1]) >= FIGURE_AREA * page.area for rect in page.images
    )


@dataclass(frozen=True)
class _Built:
    """A unit and, where it is a numbered procedure, the steps it holds.

    The steps are what lets a procedure broken by a page break be recognised as the
    continuation of the one above it rather than a second procedure.
    """

    unit: Unit
    steps: tuple[int, ...] = ()


def assemble(
    document: Document, mapping: SectionMap, *, spans: Sequence[RegionSpan] | None = None
) -> tuple[Region, ...]:
    """`Region[]` for one document: stage 5's spans filled with stage 7's units.

    `spans` is stage 5's own output where the caller already has it — deriving the regions
    walks every line of the document, and the load path wants the anchor qualities off the
    same walk for its audit.
    """
    english = {
        id(line)
        for page in document.pages
        for block in page.blocks
        if block.english
        for line in block.lines
    }
    owners = {
        id(line): id(block)
        for page in document.pages
        for block in page.blocks
        for line in block.lines
    }
    figures = {page.number: has_figures(page) for page in document.pages}
    contents = set(mapping.contents_pages)
    ordered = positions(document)

    regions = []
    for span in derive_regions(document, mapping) if spans is None else spans:
        held = [(position, line) for position, line, _ in ordered if span.contains(position)]
        built: list[_Built] = []
        for index, group in groupby(held, key=lambda item: item[0][0]):
            page = document.pages[index]
            lines = [line for _, line in group if id(line) in english]
            if not lines or page.number in contents:
                continue
            built.extend(_page_units(page, lines, owners, figures[page.number]))
        regions.append(_region(span, _joined(built)))
    return tuple(regions)


def _region(span: RegionSpan, units: list[Unit]) -> Region:
    """The page range is what the region's surviving text occupies. Stage 5's span reaches
    from one anchor to the next and can end on a page holding none of the region's words;
    citing that page would open the manual on the wrong section (6.8)."""
    pages = [page for unit in units for page in (unit.page_start, unit.page_end) if page]
    return Region(
        section_number=span.section_number,
        section_title=span.section_title,
        section_path=span.section_path,
        page_start=min(pages) if pages else span.page_start,
        page_end=max(pages) if pages else span.page_end,
        inferred=span.inferred,
        units=units,
    )


def _page_units(
    page: Page, lines: Sequence[Line], owners: Mapping[int, int], figure: bool
) -> list[_Built]:
    """One page's share of one region, in printed order.

    Segmentation runs over every line the region holds on the page, furniture marks
    included: a table cannot be detected from what is left after its rows have been dropped,
    and the mark on a row inside one is exactly what this stage exists to clear.
    """
    found = segments(page, lines=lines)
    for segment in found:
        if isinstance(segment, Table):
            for line in segment.lines:
                line.furniture = False

    built: list[_Built] = []
    for segment in found:
        built.extend(_segment_units(segment, page, owners, figure))
    return built


def _segment_units(
    segment: Segment, page: Page, owners: Mapping[int, int], figure: bool
) -> list[_Built]:
    if isinstance(segment, Table):
        return _table_units(segment, page, figure)
    return _prose_units(segment, page, owners, figure)


def _table_units(table: Table, page: Page, figure: bool) -> list[_Built]:
    built = []
    if any(heading.strip() for heading in table.heading):
        built.append(
            _built(
                table.heading_text,
                [line for row in table.heading_rows for line in row.lines],
                page,
                figure,
                atomic=True,
                repeat_on_split=True,
            )
        )
    built.extend(
        _built(table.row_text(row), row.lines, page, figure, atomic=True) for row in table.rows
    )
    return built


def _prose_units(prose: Prose, page: Page, owners: Mapping[int, int], figure: bool) -> list[_Built]:
    """Paragraphs and numbered procedures, in printed order.

    A paragraph runs to the end of its extracted block, which is where 3.5's paragraph
    boundary already is. A numbered procedure overrides that: its steps and their wrapped
    lines are one atomic unit however many blocks the enumerators were extracted into.
    """
    rows = [tuple(line for line in row if not line.furniture) for row in prose.rows]
    rows = [row for row in rows if row]

    built: list[_Built] = []
    index = 0
    while index < len(rows):
        if _step(rows[index]) is None:
            stop = index + 1
            while (
                stop < len(rows)
                and _step(rows[stop]) is None
                and owners.get(id(rows[stop][0])) == owners.get(id(rows[index][0]))
            ):
                stop += 1
            built.append(_built(_text(rows[index:stop]), _lines(rows[index:stop]), page, figure))
        else:
            stop = _procedure_end(rows, index)
            steps = tuple(step for row in rows[index:stop] if (step := _step(row)) is not None)
            built.append(
                _built(
                    _text(rows[index:stop]),
                    _lines(rows[index:stop]),
                    page,
                    figure,
                    atomic=True,
                    steps=steps,
                )
            )
        index = stop
    return built


def _procedure_end(rows: Sequence[tuple[Line, ...]], start: int) -> int:
    """Where the procedure beginning at `start` stops.

    It runs while the steps keep counting up, taking in the lines each step wraps onto: a
    continuation is set to the indent of the first step's text, and the paragraph after the
    procedure is not.
    """
    first = _step(rows[start])
    assert first is not None
    expected = first + 1
    indent = rows[start][1].bbox[0] if len(rows[start]) > 1 else rows[start][0].bbox[0]

    stop = start + 1
    while stop < len(rows):
        step = _step(rows[stop])
        if step == expected:
            expected += 1
        elif step is not None or _left(rows[stop]) < indent - INDENT_TOLERANCE:
            break
        stop += 1
    return stop


def _joined(built: Sequence[_Built]) -> list[Unit]:
    """Merge a procedure with the continuation of it printed on the next page (6.10)."""
    merged: list[_Built] = []
    for item in built:
        previous = merged[-1] if merged else None
        if previous and previous.steps and item.steps and item.steps[0] == previous.steps[-1] + 1:
            merged[-1] = _merge(previous, item)
            continue
        merged.append(item)
    return [item.unit for item in merged]


def _merge(first: _Built, second: _Built) -> _Built:
    one, two = first.unit, second.unit
    return _Built(
        unit=Unit(
            text=f"{one.text}\n{two.text}",
            page_start=one.page_start,
            page_end=two.page_end,
            atomic=True,
            repeat_on_split=one.repeat_on_split,
            flags=UnitFlags(
                degraded=one.flags.degraded or two.flags.degraded,
                has_figures=one.flags.has_figures or two.flags.has_figures,
            ),
        ),
        steps=first.steps + second.steps,
    )


def _built(
    text: str,
    lines: Sequence[Line],
    page: Page,
    figure: bool,
    *,
    atomic: bool = False,
    repeat_on_split: bool = False,
    steps: tuple[int, ...] = (),
) -> _Built:
    return _Built(
        unit=Unit(
            text=text,
            page_start=page.number,
            page_end=page.number,
            atomic=atomic,
            repeat_on_split=repeat_on_split,
            flags=UnitFlags(degraded=_degraded(lines), has_figures=figure),
        ),
        steps=steps,
    )


def _degraded(lines: Iterable[Line]) -> bool:
    """5.3: a chunk holding an unmappable span is marked, so the citation can say the
    passage contains unreadable characters."""
    return any(span.unmappable for line in lines for span in line.spans)


def _step(row: Sequence[Line]) -> int | None:
    match = _ENUMERATOR.match(_row_text(row))
    return int(match["step"]) if match else None


def _row_text(row: Sequence[Line]) -> str:
    """One printed line. A step's gutter enumerator and its text are separate extracted
    lines of one row, and 3.5 wants them read as one step."""
    return " ".join(line.text.strip() for line in row if line.text.strip())


def _text(rows: Sequence[tuple[Line, ...]]) -> str:
    return "\n".join(_row_text(row) for row in rows)


def _lines(rows: Sequence[tuple[Line, ...]]) -> list[Line]:
    return [line for row in rows for line in row]


def _left(row: Sequence[Line]) -> float:
    return min(line.bbox[0] for line in row)


__all__ = ["FIGURE_AREA", "INDENT_TOLERANCE", "assemble", "has_figures"]
