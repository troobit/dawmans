"""PyMuPDF -> Page/Line/Span, with TEXT_PRESERVE_IMAGES cleared.

Stage 2 of the run, and the only stage that opens a PDF. Everything after it annotates
the span model this module returns — furniture marks lines, glyph repair rewrites spans,
sectioning and language selection read them — so the model carries geometry rather than
flattened strings. That is what lets glyph repair key on the font name, row assembly use
bounding boxes, and language selection run per block, none of which survives a text-only
extraction.

Two things about the flag set are load-bearing (design §Extraction):

- `TEXT_PRESERVE_IMAGES` is **cleared**. PyMuPDF's default materialises every image's
  bytes into type-1 blocks; against Live 12's 96 MB of screenshots that both breaks 10.1
  (image content is read) and inflates the extraction cost 8.2 bounds. Cleared, no pixel
  data is decoded and 10.4 holds - the screenshots cost file-read time and nothing else.
  Measured on Live's p471: 52 ms with the flag, 3 ms without.
- Images are still recorded, as **placement rectangles only** (`Page.images`), from
  `page.get_image_info()`, which reports geometry without decoding pixels. 10.3's
  `has_figures` needs to know a figure is there and how big it is; it never needs what is
  in it.

Page numbers are **physical 1-based indices**, not printed page numbers. In all three
reference guides the two agree throughout, and the physical index is what CONTRACTS §3's
open-at-page action needs.

The extraction is also the fixture format: `manuals/` is gitignored, so no test may open a
reference PDF and the committed fixtures are snapshots of what this module returned
(`Document.to_dict`, `Document.from_dict`). That pins the extractor's output as an
explicit input to every downstream test.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

#: Re-exported so a test can name the bit without importing PyMuPDF, which is banned
#: outside this package (Decision 6).
PRESERVE_IMAGES = pymupdf.TEXT_PRESERVE_IMAGES

#: The dict-extraction default set, minus `TEXT_PRESERVE_IMAGES`.
EXTRACT_FLAGS = pymupdf.TEXTFLAGS_DICT & ~PRESERVE_IMAGES

#: 3.4's threshold: under this many words per page the source is ingested with `low_text`
#: set on its `SourceRecord`, never rejected. A short, heavily pictorial guide is a
#: legitimate source and a word count is not evidence that extraction failed.
LOW_TEXT_WORDS_PER_PAGE = 50

#: Snapshot schema, bumped when the on-disk fixture shape changes so a stale fixture
#: fails loudly rather than being read as something it is not.
SNAPSHOT_SCHEMA = "dawmans.pdf.extraction/1"

#: Coordinates are rounded on the way into a snapshot. Two decimal points is far finer
#: than any tolerance the layout stage uses (0.02 x page width for columns), and it keeps
#: the fixtures diffable.
_PRECISION = 2

Rect = tuple[float, float, float, float]


def _rect(values: Any) -> Rect:
    x0, y0, x1, y1 = (round(float(value), _PRECISION) for value in tuple(values)[:4])
    return (x0, y0, x1, y1)


@dataclass(slots=True)
class Span:
    """A run of characters in one font, at one size — the smallest extracted thing.

    `unmappable` is set by glyph repair (stage 4) where no mapping was found; the
    characters it names are replaced with U+FFFD and the chunk carries `degraded` (5.3).
    """

    text: str
    bbox: Rect
    font: str
    size: float
    flags: int = 0
    unmappable: bool = False

    @property
    def blank(self) -> bool:
        return not self.text.strip()


@dataclass(slots=True)
class Line:
    """One printed line. `furniture` is the mark of stage 3 (3.6).

    The mark is only ever a mark here: stages 5 and 7 clear it on lines a section anchor
    or a detected table claims, and what is still marked at the end of stage 7 is dropped.
    Text is discarded once, and never by this module.
    """

    bbox: Rect
    spans: list[Span] = field(default_factory=list)
    furniture: bool = False

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)


@dataclass(slots=True)
class Block:
    """A paragraph-ish grouping, and the granularity language selection scores (4.3).

    `lang` is what the detector returned, `english` whether the block is kept. A source
    declared with a single ISO 639-1 code is not scored at all, so both keep their
    extraction-time defaults and every block is included by declaration (4.1).
    """

    bbox: Rect
    lines: list[Line] = field(default_factory=list)
    lang: str | None = None
    english: bool = True

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass(slots=True)
class Page:
    """One physical page, numbered from 1.

    `images` holds the placement rectangle of every image drawn on the page and no pixel
    data at all. `page.get_images()` returns every XObject including logos, rules and
    background panels, so 10.3's figure test is an area threshold applied to these
    rectangles by the stage that needs it — not something this module decides.
    """

    number: int
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)
    images: list[Rect] = field(default_factory=list)

    @property
    def lines(self) -> list[Line]:
        return [line for block in self.blocks for line in block.lines]

    @property
    def spans(self) -> list[Span]:
        return [span for line in self.lines for span in line.spans]

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class TocEntry:
    """One entry of the embedded outline: `doc.get_toc()`, path A of the section map.

    `page` is the physical 1-based page the destination lands on, so it is comparable
    with `Page.number` without an offset table.
    """

    level: int
    title: str
    page: int


@dataclass(slots=True)
class Document:
    """One source's extracted span model, plus the two facts stage 5 needs about it."""

    page_count: int
    pages: list[Page] = field(default_factory=list)
    toc: list[TocEntry] = field(default_factory=list)

    @property
    def spans(self) -> list[Span]:
        return [span for page in self.pages for span in page.spans]

    @property
    def word_count(self) -> int:
        """Words over the whole extracted text layer.

        Counted **before language selection**, which is the point of 3.4: counting after
        would flag every multilingual guide for having translations. The APC guide
        averages 360 words a page extracted and roughly a quarter of that once the
        Spanish, French, Italian and German pages are dropped.
        """
        return sum(len(span.text.split()) for span in self.spans)

    @property
    def low_text(self) -> bool:
        """3.4: fewer than 50 words per page averaged across the document.

        A flag, not a rejection - it is reported in the inventory (9.1) and nothing in
        retrieval, ranking or synthesis consumes it.
        """
        if self.page_count <= 0:
            return True
        return self.word_count / self.page_count < LOW_TEXT_WORDS_PER_PAGE

    @property
    def has_text_layer(self) -> bool:
        """3.3: a source with no embedded text layer at all is rejected, not indexed empty.

        The test is a non-blank span on a line that is not page furniture, anywhere in the
        document. Furniture is where a scanned manual's only extractable text tends to be
        - a stamped page number over an image - and indexing a source for that alone is
        exactly the empty index 3.3 forbids.
        """
        return any(
            not span.blank
            for page in self.pages
            for line in page.lines
            if not line.furniture
            for span in line.spans
        )

    def to_dict(self) -> dict[str, Any]:
        """The committed-fixture form. Stage annotations are written only where set, so a
        snapshot of a fresh extraction carries none of them."""
        return {
            "schema": SNAPSHOT_SCHEMA,
            "page_count": self.page_count,
            "toc": [[entry.level, entry.title, entry.page] for entry in self.toc],
            "pages": [_page_to_dict(page) for page in self.pages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Document:
        schema = data.get("schema")
        if schema != SNAPSHOT_SCHEMA:
            raise ValueError(f"expected snapshot schema {SNAPSHOT_SCHEMA!r}, found {schema!r}")
        return cls(
            page_count=int(data["page_count"]),
            pages=[_page_from_dict(page) for page in data["pages"]],
            toc=[
                TocEntry(level=int(e[0]), title=e[1], page=int(e[2])) for e in data.get("toc", ())
            ],
        )


def _page_to_dict(page: Page) -> dict[str, Any]:
    return {
        "number": page.number,
        "width": round(page.width, _PRECISION),
        "height": round(page.height, _PRECISION),
        "images": [list(rect) for rect in page.images],
        "blocks": [
            {
                "bbox": list(block.bbox),
                **({"lang": block.lang} if block.lang is not None else {}),
                **({"english": block.english} if not block.english else {}),
                "lines": [
                    {
                        "bbox": list(line.bbox),
                        **({"furniture": True} if line.furniture else {}),
                        "spans": [
                            {
                                "text": span.text,
                                "bbox": list(span.bbox),
                                "font": span.font,
                                "size": round(span.size, _PRECISION),
                                "flags": span.flags,
                                **({"unmappable": True} if span.unmappable else {}),
                            }
                            for span in line.spans
                        ],
                    }
                    for line in block.lines
                ],
            }
            for block in page.blocks
        ],
    }


def _page_from_dict(data: dict[str, Any]) -> Page:
    return Page(
        number=int(data["number"]),
        width=float(data["width"]),
        height=float(data["height"]),
        images=[_rect(rect) for rect in data.get("images", ())],
        blocks=[
            Block(
                bbox=_rect(block["bbox"]),
                lang=block.get("lang"),
                english=bool(block.get("english", True)),
                lines=[
                    Line(
                        bbox=_rect(line["bbox"]),
                        furniture=bool(line.get("furniture", False)),
                        spans=[
                            Span(
                                text=span["text"],
                                bbox=_rect(span["bbox"]),
                                font=span["font"],
                                size=float(span["size"]),
                                flags=int(span.get("flags", 0)),
                                unmappable=bool(span.get("unmappable", False)),
                            )
                            for span in line["spans"]
                        ],
                    )
                    for line in block["lines"]
                ],
            )
            for block in data["blocks"]
        ],
    )


def extract_page(page: Any, number: int) -> Page:
    """One PyMuPDF page into the span model. `number` is the physical 1-based index."""
    content = page.get_text("dict", flags=EXTRACT_FLAGS)
    blocks = []
    for block in content["blocks"]:
        # With `TEXT_PRESERVE_IMAGES` cleared there are no type-1 blocks to skip. The
        # guard stays because the flag set is the only thing standing between this loop
        # and a decoded screenshot, and a silent change to it should not reach the index.
        if block.get("type") != 0:
            continue
        lines = [
            Line(
                bbox=_rect(line["bbox"]),
                spans=[
                    Span(
                        text=span["text"],
                        bbox=_rect(span["bbox"]),
                        font=span["font"],
                        size=round(float(span["size"]), _PRECISION),
                        flags=int(span.get("flags", 0)),
                    )
                    for span in line["spans"]
                ],
            )
            for line in block["lines"]
        ]
        blocks.append(Block(bbox=_rect(block["bbox"]), lines=lines))

    return Page(
        number=number,
        width=round(float(content["width"]), _PRECISION),
        height=round(float(content["height"]), _PRECISION),
        blocks=blocks,
        images=[_rect(image["bbox"]) for image in page.get_image_info()],
    )


def extract_document(path: Path, pages: Iterable[int] | None = None) -> Document:
    """Extract `path`. `pages` selects physical 1-based page numbers, for fixture capture.

    `page_count` is always the document's own, even when only a slice is extracted: 3.4
    divides by it, and the audit of 4.4 reports against it.
    """
    with pymupdf.open(path) as doc:
        wanted = range(1, doc.page_count + 1) if pages is None else pages
        return Document(
            page_count=doc.page_count,
            pages=[extract_page(doc[number - 1], number) for number in wanted],
            toc=[
                TocEntry(level=int(level), title=title, page=int(target))
                for level, title, target in doc.get_toc()
            ],
        )


__all__ = [
    "EXTRACT_FLAGS",
    "LOW_TEXT_WORDS_PER_PAGE",
    "PRESERVE_IMAGES",
    "SNAPSHOT_SCHEMA",
    "Block",
    "Document",
    "Line",
    "Page",
    "Rect",
    "Span",
    "TocEntry",
    "extract_document",
    "extract_page",
]
