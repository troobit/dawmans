"""Hand-built span models, for the stages that annotate one rather than produce it.

`pdfgen.py` writes PDFs for the extraction tests. Everything after extraction takes a
`Document` and marks it — furniture marks lines, glyph repair rewrites spans, language
selection scores blocks — so those tests want a document with known geometry and known
text, and no PDF at all.

Coordinates match the extractor's: `y` grows downward from the top of the page, and the
page box is the reference guides' 396x612 unless a test says otherwise.
"""

from __future__ import annotations

from collections.abc import Iterable

from dawmans.corpus.pdf.extract import Block, Document, Line, Page, Span

#: The APC guide's body face, and the Wingdings 3 run set beside it on p14.
BODY = "HelveticaNeue-Roman"
SYMBOL = "Wingdings3"

WIDTH = 396.0
HEIGHT = 612.0
LEADING = 13.2


def span(
    text: str,
    *,
    font: str = BODY,
    size: float = 10.0,
    x0: float = 72.0,
    top: float = 100.0,
    width: float = 250.0,
    height: float = 9.3,
) -> Span:
    return Span(text=text, bbox=(x0, top, x0 + width, top + height), font=font, size=size)


def text_line(
    text: str,
    *,
    top: float,
    x0: float = 72.0,
    width: float = 250.0,
    height: float = 9.3,
    font: str = BODY,
    size: float = 10.0,
) -> Line:
    """One printed line holding one span."""
    return Line(
        bbox=(x0, top, x0 + width, top + height),
        spans=[span(text, font=font, size=size, x0=x0, top=top, width=width, height=height)],
    )


def line_of(spans: Iterable[Span]) -> Line:
    """One printed line holding several spans — a run of symbols inside prose."""
    spans = list(spans)
    return Line(
        bbox=(
            min(s.bbox[0] for s in spans),
            min(s.bbox[1] for s in spans),
            max(s.bbox[2] for s in spans),
            max(s.bbox[3] for s in spans),
        ),
        spans=spans,
    )


def block_of(*lines: Line) -> Block:
    return Block(
        bbox=(
            min(line.bbox[0] for line in lines),
            min(line.bbox[1] for line in lines),
            max(line.bbox[2] for line in lines),
            max(line.bbox[3] for line in lines),
        ),
        lines=list(lines),
    )


def text_block(text: str, *, top: float = 100.0, x0: float = 72.0, width: float = 250.0) -> Block:
    """A block of one line — the granularity language selection scores."""
    return block_of(text_line(text, top=top, x0=x0, width=width))


def paragraph(*bodies: str, top: float = 100.0, x0: float = 72.0) -> Block:
    """Successive lines down the page, as a paragraph is set."""
    return block_of(
        *(text_line(body, top=top + index * LEADING, x0=x0) for index, body in enumerate(bodies))
    )


def page_of(number: int, *blocks: Block, width: float = WIDTH, height: float = HEIGHT) -> Page:
    return Page(number=number, width=width, height=height, blocks=list(blocks))


def document_of(*pages: Page, page_count: int | None = None) -> Document:
    return Document(page_count=page_count or len(pages), pages=list(pages))


def header(text: str, *, height: float = HEIGHT, x0: float = 72.0) -> Block:
    """A line wholly inside the top 8% of the page box."""
    return block_of(text_line(text, top=height * 0.02, x0=x0, width=80.0))


def footer(text: str, *, height: float = HEIGHT, x0: float = 320.0) -> Block:
    """A line wholly inside the bottom 8% of the page box, where a page number sits."""
    return block_of(text_line(text, top=height * 0.94, x0=x0, width=20.0))
