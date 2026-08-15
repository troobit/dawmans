"""Outline / printed-TOC / heading-style -> SectionMap, and heading anchoring.

Stage 5 of the run, and the stage a citation stands or falls on: a chunk carries the
section it belongs to, so getting the section wrong renames every chunk inside it.

Three sources of structure, tried in order. All three are content-side; none of them is
per-manual configuration, which is 6.6:

| Path | Trigger |
|---|---|
| **A. Embedded outline** | `doc.get_toc()` returns >=2 entries |
| **B. Printed contents page** | a page whose lines are >=60% dot-leader matches |
| **C. Heading styles** | a style that clears the quality gate below |

Every manual in this corpus carries an embedded outline, so path A fires for all four and
paths B and C have no live instance (design §Section map, corpus check 2026-08-15). They
are what the next manual needs, and their fixtures are captured with the outline withheld.

**Path C's gate is written to fail closed.** "Two spans larger than the body style" is met
by almost any PDF — a cover title alone clears it — and the danger is path C firing
*wrongly*: a title plus a strapline yields two regions spanning the whole document and
every citation inside them names a wrong section. A candidate style qualifies only when its
spans start a line, are shorter than 60% of the modal line length, do not end in a full
stop, and number >=4 spread over >=40% of the document's pages at a rate of at least one
per ten pages. Spread and rate are two different tests: spread is first-to-last heading
against the document, so four headings on the cover fail it; rate is the count against the
page count, so four headings in a 60-page guide fail that. A document that fails the gate
becomes one titled region under 6.4/6.5 — weak citations, which the requirements
anticipate, rather than confident wrong ones.

**Printed contents pages are excluded from chunking on every document**, not only when path
B is the chosen path. Dot leaders are one form and not the only one: Live sets its contents
page numbers as a separate right-hand column of bare numerals, so the test that catches
them is a page whose lines are predominantly either a bare numeral in a right-hand band or
a title paired with one. Live's printed contents is pp2-21, some 12 chunks that between
them contain every section title in the document; they BM25-match precisely the verbatim
identifier queries this corpus exists to serve. The pages stay in `page_count` and in the
4.4 audit — only their text is dropped, by stage 7.

**Anchoring is the load-bearing part.** Live averages 1.2 TOC entries per page, so
attributing text to a section by page number alone would put several sections under one
heading. Each entry is resolved to the line its heading is printed on, and anchoring is the
stage-5 half of the mark-then-clear ordering: a line an anchor resolves to has its furniture
mark cleared, because a chapter title printed in the header band is both.

There is no back-matter region on any of the three paths: the last entry's region runs to
the end of the document, so the only run of pages belonging to no section is the one before
the first anchor. `FRONT_MATTER` is therefore the only default name this module needs.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from statistics import median

from dawmans.corpus.pdf.extract import Document, Line, Page

# --- The three paths -------------------------------------------------------------------

PATH_OUTLINE = "outline"
PATH_CONTENTS = "contents"
PATH_HEADINGS = "headings"
PATH_NONE = "none"

#: Path A's trigger. One entry is a PDF linking to its own cover, which is not a structure.
OUTLINE_MIN_ENTRIES = 2

#: 6.3's threshold: at or above this share of entries carrying a parsed number the document
#: is numbered; below it every region is unnumbered and no number is invented (6.4).
NUMBERED_RATIO = 0.6

# --- Printed contents pages ---------------------------------------------------------------

#: The share of a page's lines that must read as contents entries.
CONTENTS_RATIO = 0.6

#: How many page references a contents page must carry. Three lines that happen to end in a
#: numeral are not a table of contents, and suppressing a page is invisible in the output.
CONTENTS_MIN_ENTRIES = 5

#: A page reference sits in the right-hand band, as a fraction of page width. The Nitro Max
#: MIDI note table's numeric column is at 0.74 and Live's contents numerals at 0.86.
RIGHT_BAND = 0.8

# --- Path C's quality gate -----------------------------------------------------------------

HEADING_MIN_COUNT = 4
HEADING_SPREAD = 0.4
HEADING_PAGES_EACH = 10
HEADING_MAX_LENGTH = 0.6

_NUMBER = re.compile(r"^\(?(?P<number>\d+(?:\.\d+)*)\)?[.\s]\s*(?P<title>\S.*)$")
_DOT_LEADER = re.compile(
    r"^\(?(?P<number>\d+(?:\.\d+)*)?\)?\s*(?P<title>\S.*?)[\s.]{3,}(?P<page>\d+)$"
)
_WHITESPACE = re.compile(r"\s+")

#: 6.5's default name for a run of pages belonging to no section.
FRONT_MATTER = "Front matter"

#: Where an anchor was found, for the run report: on the target page, on the page either
#: side of it, or nowhere — `page-only` is weak sectioning made visible rather than silent.
ANCHOR_TITLE = "title"
ANCHOR_NEARBY = "nearby"
ANCHOR_PAGE_ONLY = "page-only"

#: A line's place in the document: page index, then its top and left edges. A geometric
#: position rather than an index into a list, because stage 5 orders lines by reading order
#: and stage 7 orders them by row, and both have to agree on where a region starts.
Position = tuple[int, float, float]


def normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().casefold()


def parse_section_number(printed: str) -> tuple[str | None, str]:
    """`24.1 An Overview of Racks` and `(1.3.1) Connection Diagram` into number and title.

    The number comes off the title because the citation renders the two separately: leaving
    it in renders `§24.1 24.1 An Overview of Racks`. A title with no number is returned
    whole, which is 6.4's case.
    """
    match = _NUMBER.match(printed.strip())
    if match is None:
        return None, printed.strip()
    return match["number"], match["title"].strip()


def render_section(number: str, title: str) -> str:
    """The inverse of `parse_section_number` on the pair, for the round-trip property."""
    return f"{number} {title}"


def reading_lines(page: Page) -> list[Line]:
    """The page's non-blank lines, top to bottom and left to right.

    Extraction order is block order, which is neither: on Live's contents page every page
    numeral is extracted before any title, and on a procedure page the step enumerators
    come after the step text.
    """
    return sorted(
        (line for line in page.lines if line.text.strip()),
        key=lambda line: (line.bbox[1], line.bbox[0]),
    )


def positions(document: Document) -> list[tuple[Position, Line, int]]:
    """Every non-blank line of the document in reading order, with its position and page."""
    return [
        ((index, line.bbox[1], line.bbox[0]), line, page.number)
        for index, page in enumerate(document.pages)
        for line in reading_lines(page)
    ]


# --- The body style, and what reads as a title against it ----------------------------------


@dataclass(frozen=True)
class BodyStyle:
    """The style most of the document's text is set in, and how long its lines run."""

    font: str
    size: float
    line_length: float

    @property
    def heading_length(self) -> float:
        """`shorter than 60% of the modal line length`: a heading is set to its own width
        and a paragraph runs the measure, whatever face either is in."""
        return self.line_length * HEADING_MAX_LENGTH


def body_style(document: Document) -> BodyStyle | None:
    """The `(font, size)` carrying the most lines, and the median length of those lines.

    Furniture is excluded: a running header is on every page and would be the modal style of
    a document that is mostly figures.
    """
    counts: Counter[tuple[str, float]] = Counter()
    lengths: dict[tuple[str, float], list[int]] = {}
    for page in document.pages:
        for line in page.lines:
            text = line.text.strip()
            if not text or line.furniture or not line.spans:
                continue
            style = (line.spans[0].font, line.spans[0].size)
            counts[style] += 1
            lengths.setdefault(style, []).append(len(text))

    if not counts:
        return None
    (font, size), _ = counts.most_common(1)[0]
    return BodyStyle(font=font, size=size, line_length=float(median(lengths[(font, size)])))


def reads_as_title(line: Line, body: BodyStyle | None) -> bool:
    """Path C's style test, applied to one line — 6.5 names a titled region with it too."""
    text = line.text.strip()
    if not text or line.furniture or not line.spans or body is None:
        return False
    lead = line.spans[0]
    return (
        lead.size > body.size
        and len(text) < body.heading_length
        and not text.endswith(".")
        and lead.text.strip() != ""
    )


# --- Printed contents pages -----------------------------------------------------------------


def _page_numeral(line: Line, page: Page, page_count: int) -> bool:
    """A bare numeral in the right-hand band that could be a page of this document."""
    text = line.text.strip()
    if not text.isdigit() or line.bbox[0] < page.width * RIGHT_BAND:
        return False
    return 1 <= int(text) <= page_count


def _shares_a_row(line: Line, others: list[Line]) -> bool:
    return any(
        line.bbox[1] < other.bbox[3] and other.bbox[1] < line.bbox[3]
        for other in others
        if other is not line
    )


def dot_leader_entries(page: Page) -> list[tuple[str | None, str, int]]:
    """Path B's grammar over one page: `(1.3.1) Connection Diagram ...... 5`."""
    entries = []
    for line in reading_lines(page):
        match = _DOT_LEADER.match(line.text.strip())
        if match is not None:
            entries.append((match["number"], match["title"].strip(), int(match["page"])))
    return entries


def is_dot_leader_page(page: Page) -> bool:
    """Path B's trigger: a page whose lines are >=60% dot-leader matches."""
    lines = [line for line in reading_lines(page) if not line.furniture]
    leaders = dot_leader_entries(page)
    return (
        len(leaders) >= CONTENTS_MIN_ENTRIES
        and len(lines) > 0
        and len(leaders) >= len(lines) * CONTENTS_RATIO
    )


def is_contents_page(page: Page, page_count: int) -> bool:
    """Whether this page is a printed table of contents, in either of its two forms.

    The right-hand-numeral form is what catches Live, whose contents pages carry no dot
    leaders at all. The two guards against a false positive are the band — the Nitro Max
    MIDI note table's numeric column is in the body of the page — and the range, since 36
    to 58 are not page numbers of a 35-page guide.
    """
    lines = [line for line in reading_lines(page) if not line.furniture]
    if len(lines) < CONTENTS_MIN_ENTRIES:
        return False

    numerals = [line for line in lines if _page_numeral(line, page, page_count)]
    leaders = {id(line) for line in lines if _DOT_LEADER.match(line.text.strip())}
    if len(numerals) + len(leaders) < CONTENTS_MIN_ENTRIES:
        return False

    entries = sum(
        1
        for line in lines
        if id(line) in leaders or line in numerals or _shares_a_row(line, numerals)
    )
    return entries >= len(lines) * CONTENTS_RATIO


def contents_pages(document: Document) -> frozenset[int]:
    return frozenset(
        page.number for page in document.pages if is_contents_page(page, document.page_count)
    )


# --- Path C: heading styles -------------------------------------------------------------------


@dataclass(frozen=True)
class HeadingStyle:
    """A style that cleared the quality gate, and what it was measured on."""

    font: str
    size: float
    count: int
    pages: tuple[int, ...]

    @property
    def style(self) -> tuple[str, float]:
        return (self.font, self.size)


def _heading_lines(document: Document, style: tuple[str, float], body: BodyStyle) -> list[Line]:
    """The lines this style opens that could be headings at all."""
    return [
        line
        for page in document.pages
        for line in reading_lines(page)
        if not line.furniture
        and line.spans
        and (line.spans[0].font, line.spans[0].size) == style
        and len(line.text.strip()) < body.heading_length
        and not line.text.strip().endswith(".")
    ]


def heading_style(document: Document) -> HeadingStyle | None:
    """The largest style that clears path C's gate, or `None` — which is the usual answer.

    A style is only a candidate where it is set larger than the body; equal-size bold runs
    are emphasis, and treating them as structure is how a manual acquires a section per
    paragraph.
    """
    body = body_style(document)
    if body is None:
        return None

    pages = len(document.pages)
    candidates: dict[tuple[str, float], list[int]] = {}
    for index, page in enumerate(document.pages):
        for line in reading_lines(page):
            if line.furniture or not line.spans:
                continue
            style = (line.spans[0].font, line.spans[0].size)
            if style[1] > body.size:
                candidates.setdefault(style, []).append(index)

    qualifying: list[HeadingStyle] = []
    for style in sorted(candidates, key=lambda style: style[1], reverse=True):
        lines = _heading_lines(document, style, body)
        if not lines:
            continue
        found = sorted(
            {
                index
                for index, page in enumerate(document.pages)
                if any(line in lines for line in reading_lines(page))
            }
        )
        count = len(lines)
        spread = found[-1] - found[0] + 1
        if (
            count >= HEADING_MIN_COUNT
            and spread >= pages * HEADING_SPREAD
            and count >= pages / HEADING_PAGES_EACH
        ):
            qualifying.append(
                HeadingStyle(
                    font=style[0],
                    size=style[1],
                    count=count,
                    pages=tuple(document.pages[index].number for index in found),
                )
            )

    return qualifying[0] if qualifying else None


# --- The map ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionEntry:
    """One entry of the document's own structure, whichever path found it."""

    level: int
    number: str | None
    title: str  # the leaf title, with any printed number taken off it
    page: int  # physical 1-based
    path: tuple[str, ...] = ()  # ancestor titles, nearest two, outermost first


@dataclass(frozen=True)
class SectionMap:
    """What stage 5 knows about a document before anything is anchored to a line."""

    entries: tuple[SectionEntry, ...] = ()
    path: str = PATH_NONE
    numbered: bool = False
    inferred: bool = False
    contents_pages: frozenset[int] = frozenset()
    heading_count: int = 0
    heading_style: tuple[str, float] | None = None

    def to_dict(self) -> dict[str, object]:
        """The part of the ingestion audit this stage owns."""
        return {
            "path": self.path,
            "sections": len(self.entries),
            "numbered": self.numbered,
            "inferred": self.inferred,
            "contents_pages": sorted(self.contents_pages),
            "heading_count": self.heading_count,
            "heading_style": list(self.heading_style) if self.heading_style else None,
        }


def _with_parents(raw: list[tuple[int, str | None, str, int]]) -> tuple[SectionEntry, ...]:
    """Attach each entry's nearest two ancestors, from the levels."""
    entries: list[SectionEntry] = []
    stack: list[tuple[int, str]] = []
    for level, number, title, page in raw:
        while stack and stack[-1][0] >= level:
            stack.pop()
        entries.append(
            SectionEntry(
                level=level,
                number=number,
                title=title,
                page=page,
                path=tuple(title for _, title in stack[-2:]),
            )
        )
        stack.append((level, title))
    return tuple(entries)


def _numbered(entries: tuple[SectionEntry, ...]) -> bool:
    if not entries:
        return False
    carried = sum(1 for entry in entries if entry.number is not None)
    return carried >= len(entries) * NUMBERED_RATIO


def _unnumber(entries: tuple[SectionEntry, ...]) -> tuple[SectionEntry, ...]:
    """6.4: a document below the threshold invents no number for the entries that had one."""
    return tuple(
        SectionEntry(
            level=entry.level, number=None, title=entry.title, page=entry.page, path=entry.path
        )
        for entry in entries
    )


def _outline_entries(document: Document) -> list[tuple[int, str | None, str, int]]:
    raw = []
    for entry in document.toc:
        number, title = parse_section_number(entry.title)
        raw.append((entry.level, number, title, entry.page))
    return raw


def _contents_entries(document: Document) -> list[tuple[int, str | None, str, int]]:
    for page in document.pages:
        if not is_dot_leader_page(page):
            continue
        return [
            (number.count(".") + 1 if number else 1, number, title, target)
            for number, title, target in dot_leader_entries(page)
        ]
    return []


def _heading_entries(
    document: Document, style: HeadingStyle
) -> list[tuple[int, str | None, str, int]]:
    body = body_style(document)
    assert body is not None  # heading_style() returned a style, so there is a body style
    raw = []
    for page in document.pages:
        for line in _heading_lines(document, style.style, body):
            if line in reading_lines(page):
                number, title = parse_section_number(line.text)
                raw.append((1, number, title, page.number))
    return raw


def section_map(document: Document) -> SectionMap:
    """The document's structure, from whichever of the three paths finds one first."""
    excluded = contents_pages(document)

    if len(document.toc) >= OUTLINE_MIN_ENTRIES:
        return _map(_outline_entries(document), PATH_OUTLINE, excluded, inferred=False)

    contents = _contents_entries(document)
    if contents:
        return _map(contents, PATH_CONTENTS, excluded, inferred=False)

    style = heading_style(document)
    if style is not None:
        return _map(
            _heading_entries(document, style),
            PATH_HEADINGS,
            excluded,
            inferred=True,
            heading_count=style.count,
            heading_style=style.style,
        )

    return SectionMap(path=PATH_NONE, contents_pages=excluded)


def _map(
    raw: list[tuple[int, str | None, str, int]],
    path: str,
    excluded: frozenset[int],
    *,
    inferred: bool,
    heading_count: int = 0,
    heading_style: tuple[str, float] | None = None,
) -> SectionMap:
    entries = _with_parents(raw)
    numbered = _numbered(entries)
    return SectionMap(
        entries=entries if numbered else _unnumber(entries),
        path=path,
        numbered=numbered,
        inferred=inferred,
        contents_pages=excluded,
        heading_count=heading_count,
        heading_style=heading_style,
    )


# --- Anchoring ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    """Where one entry's section actually starts, and how confidently that was found."""

    entry: SectionEntry
    position: Position
    quality: str


def _index_of(document: Document, number: int) -> int | None:
    for index, page in enumerate(document.pages):
        if page.number == number:
            return index
    return None


def _target_index(document: Document, number: int) -> int:
    """The page an entry lands on, or the nearest one present.

    A fixture is a slice of its manual, so the page an outline entry names is not always
    extracted; the entry still has to anchor somewhere, and the first page at or after it is
    the only answer that keeps the entries in order.
    """
    for index, page in enumerate(document.pages):
        if page.number >= number:
            return index
    return max(len(document.pages) - 1, 0)


def _scan(
    lines: list[Line], index: int, wanted: str, previous: Position | None
) -> tuple[Position, Line] | None:
    """The first line of this page whose title reads as `wanted`, after `previous`."""
    for line in lines:
        position = (index, line.bbox[1], line.bbox[0])
        if previous is not None and position <= previous:
            continue
        printed = normalise(line.text)
        titled = normalise(parse_section_number(line.text)[1])
        if printed.startswith(wanted) or titled.startswith(wanted):
            return position, line
    return None


def anchor_entries(document: Document, entries: tuple[SectionEntry, ...]) -> tuple[Anchor, ...]:
    """Resolve every entry to the line its heading is printed on, in document order.

    The scan order is the design's: a normalised prefix match on the target page at or after
    the previous entry's position, then the page either side of it, then the top of the
    target page with `page-only` recorded so weak sectioning is visible rather than silent.
    Live prints its in-body headings with their numbers (`24.1 An Overview of Racks`), so the
    first attempt succeeds for the overwhelming majority of its 1054 entries.

    Anchors are monotonic by construction: an entry that would resolve before its
    predecessor is clamped to it, because regions are half-open intervals between successive
    anchors and an anchor that goes backwards makes two of them overlap.
    """
    by_page = [reading_lines(page) for page in document.pages]
    anchors: list[Anchor] = []
    previous: Position | None = None

    for entry in entries:
        anchor = _anchor(document, by_page, entry, previous)
        if previous is not None and anchor.position < previous:
            anchor = Anchor(entry=entry, position=previous, quality=ANCHOR_PAGE_ONLY)
        anchors.append(anchor)
        previous = anchor.position
    return tuple(anchors)


def _anchor(
    document: Document, by_page: list[list[Line]], entry: SectionEntry, previous: Position | None
) -> Anchor:
    target = _target_index(document, entry.page)
    wanted = normalise(entry.title)
    if wanted:
        nearby = [_index_of(document, entry.page - 1), _index_of(document, entry.page + 1)]
        for index, quality in [(target, ANCHOR_TITLE)] + [
            (index, ANCHOR_NEARBY) for index in nearby if index is not None
        ]:
            found = _scan(by_page[index], index, wanted, previous)
            if found is not None:
                position, line = found
                line.furniture = False  # the stage-5 half of mark-then-clear
                return Anchor(entry=entry, position=position, quality=quality)

    return Anchor(entry=entry, position=(target, 0.0, 0.0), quality=ANCHOR_PAGE_ONLY)


# --- Regions ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class RegionSpan:
    """One section, or one titled region — the half-open run of lines that belongs to it.

    This is stage 5's output and the precursor of `loader.Region`: stage 7 fills in the units
    once furniture has been dropped and tables assembled.
    """

    section_number: str | None
    section_title: str
    section_path: tuple[str, ...]
    start: Position
    end: Position
    inferred: bool
    page_start: int
    page_end: int
    anchor: str

    def contains(self, position: Position) -> bool:
        return self.start <= position < self.end


def _titled(lines: list[Line], body: BodyStyle | None) -> str:
    """6.5: a run of pages belonging to no section is named by its own printed title."""
    for line in lines:
        if reads_as_title(line, body):
            return parse_section_number(line.text)[1]
    return FRONT_MATTER


def derive_regions(document: Document, mapping: SectionMap) -> tuple[RegionSpan, ...]:
    """The document as an ordered, non-overlapping run of regions covering every line.

    A region runs from its anchor to the next anchor in document order, so a page shared by
    two sections splits between them — which is the whole reason anchoring exists. There is
    no back-matter region: the last entry's region runs to the end of the document, so the
    only run of pages belonging to no section is the one before the first anchor.
    """
    ordered = positions(document)
    if not ordered:
        return ()

    body = body_style(document)
    anchors = anchor_entries(document, mapping.entries)
    end_of_document = (len(document.pages), 0.0, 0.0)

    bounds: list[tuple[Position, Position, Anchor | None]] = []
    starts = [anchor.position for anchor in anchors] + [end_of_document]
    if ordered[0][0] < starts[0]:
        bounds.append((ordered[0][0], starts[0], None))
    for index, anchor in enumerate(anchors):
        bounds.append((anchor.position, starts[index + 1], anchor))

    regions = []
    for start, end, anchor in bounds:
        held = [(line, page) for position, line, page in ordered if start <= position < end]
        pages = [page for _, page in held] or [document.pages[start[0]].number]
        if anchor is None:
            regions.append(
                RegionSpan(
                    section_number=None,
                    section_title=_titled([line for line, _ in held], body),
                    section_path=(),
                    start=start,
                    end=end,
                    inferred=False,
                    page_start=min(pages),
                    page_end=max(pages),
                    anchor=FRONT_MATTER,
                )
            )
            continue
        regions.append(
            RegionSpan(
                section_number=anchor.entry.number,
                section_title=anchor.entry.title,
                section_path=anchor.entry.path,
                start=start,
                end=end,
                inferred=mapping.inferred,
                page_start=min(pages),
                page_end=max(pages),
                anchor=anchor.quality,
            )
        )
    return tuple(regions)


__all__ = [
    "ANCHOR_NEARBY",
    "ANCHOR_PAGE_ONLY",
    "ANCHOR_TITLE",
    "CONTENTS_MIN_ENTRIES",
    "CONTENTS_RATIO",
    "FRONT_MATTER",
    "HEADING_MAX_LENGTH",
    "HEADING_MIN_COUNT",
    "HEADING_PAGES_EACH",
    "HEADING_SPREAD",
    "NUMBERED_RATIO",
    "OUTLINE_MIN_ENTRIES",
    "PATH_CONTENTS",
    "PATH_HEADINGS",
    "PATH_NONE",
    "PATH_OUTLINE",
    "RIGHT_BAND",
    "BodyStyle",
    "HeadingStyle",
    "Position",
    "SectionEntry",
    "SectionMap",
    "body_style",
    "contents_pages",
    "dot_leader_entries",
    "heading_style",
    "is_contents_page",
    "is_dot_leader_page",
    "normalise",
    "parse_section_number",
    "positions",
    "reading_lines",
    "reads_as_title",
    "render_section",
]
