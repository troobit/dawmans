"""Repeated page furniture — requirement 3.6, stage 3 of the run.

Running headers, running footers and standalone page numbers are printed on every page and
belong to none of them. Left in, they land inside quoted answers: a citation reading
"…press Play. Ableton Live 12 Reference Manual 471 The Session View…" is the failure 3.6
names.

**This stage only marks.** `Line.furniture` is a mark, not a deletion, and two later stages
clear it again: stage 5 on any line a section anchor resolves to (a chapter title printed
in the header band is both furniture and a heading), and stage 7 on any line inside a
detected table (a table that reaches into the band prints numbers there that are data).
What is still marked at the end of stage 7 is dropped. Text is therefore discarded exactly
once, and never here.

Two rules, over lines lying wholly inside the top or bottom 8% of the page box:

1. **Repeated key.** Normalise the line to a key — casefold, collapse whitespace, digit
   runs to `#` — and mark it where the key occurs on >=60% of pages, or on >=5 pages of a
   document of <=10, at a consistent y-band. Digit collapsing is what makes `471` on p471
   and `472` on p472 one key rather than two.
2. **Digits only.** A line in those bands whose text is only digits is marked once its key
   occurs on more than one page, without the 60% threshold and without the band-consistency
   test. This is the lenient rule, for the guide that prints its number on some pages only.

Both rules stop at more than one page, which is the safety property (design
§Property-based tests): a line whose key occurs on exactly one page is not repeated
boilerplate, whatever it looks like, and is never suppressed. The design states the
digits-only rule without a repetition bound; taken literally that would suppress a lone
numeral in the band on a single page, which the property forbids, so the bound is applied
to both rules.

On this corpus the digits-only rule is the one that does the work — all three reference
guides print a bare page number and nothing else in the band — and the repeated-key rule is
there for the next manual that prints a running title.
"""

from __future__ import annotations

import re
from collections import defaultdict

from dawmans.corpus.pdf.extract import Document, Line, Page

#: The candidate bands, as a fraction of page height, measured from each edge.
BAND = 0.08

#: A key on this fraction of the document's pages is furniture.
REPEAT_RATIO = 0.6

#: In a document of at most `SHORT_DOCUMENT_PAGES` pages, this many pages is enough on its
#: own: 60% of a ten-page guide is six pages, and a header on five of them is still a
#: header.
SHORT_DOCUMENT_PAGES = 10
SHORT_DOCUMENT_REPEATS = 5

#: Occurrences of one key count as a consistent y-band when their offsets from the page
#: edge, as a fraction of page height, differ by no more than this. A running header sits
#: at the same height on every page; a heading that happens to recur drifts.
BAND_TOLERANCE = 0.02

_DIGIT_RUN = re.compile(r"[0-9]+")
_WHITESPACE = re.compile(r"\s+")


def key_of(text: str) -> str:
    """The normalised form two pages' furniture has to share.

    Digits are `[0-9]`, not `\\d`: `\\d` matches other scripts' digits and would fold a
    line of Arabic-Indic numerals into the same key as a page number.
    """
    return _DIGIT_RUN.sub("#", _WHITESPACE.sub(" ", text).strip().casefold())


def in_band(line: Line, page: Page) -> bool:
    """Whether `line` lies wholly inside the top or bottom band of the page box."""
    band = page.height * BAND
    return line.bbox[3] <= band or line.bbox[1] >= page.height - band


def _band_offset(line: Line, page: Page) -> float:
    """The line's distance from its own edge of the page, as a fraction of page height.

    Measuring from the nearer edge rather than from the top means a header and a footer are
    never mistaken for one key at one height, and a page of a different size in the same
    document still compares.
    """
    if line.bbox[3] <= page.height * BAND:
        return line.bbox[1] / page.height
    return (page.height - line.bbox[3]) / page.height


def mark_furniture(document: Document) -> int:
    """Mark the furniture lines of `document` in place. Returns how many were marked."""
    candidates: dict[str, list[tuple[int, float, Line]]] = defaultdict(list)
    for page in document.pages:
        for line in page.lines:
            text = line.text.strip()
            if text and in_band(line, page):
                candidates[key_of(text)].append((page.number, _band_offset(line, page), line))

    pages = len(document.pages)
    marked = 0
    for key, occurrences in candidates.items():
        if len({number for number, _, _ in occurrences}) < 2:
            continue  # the safety property: one page is not repetition
        if _repeats(occurrences, pages) or _digits_only(key):
            for _, _, line in occurrences:
                line.furniture = True
                marked += 1
    return marked


def _repeats(occurrences: list[tuple[int, float, Line]], pages: int) -> bool:
    """Rule 1: enough pages, at a consistent height."""
    on = len({number for number, _, _ in occurrences})
    frequent = on >= pages * REPEAT_RATIO or (
        pages <= SHORT_DOCUMENT_PAGES and on >= SHORT_DOCUMENT_REPEATS
    )
    offsets = [offset for _, offset, _ in occurrences]
    return frequent and max(offsets) - min(offsets) <= BAND_TOLERANCE


def _digits_only(key: str) -> bool:
    """Rule 2. Every digit run has already collapsed to `#`, so a page number of any
    length is this one key, and `3.4` — which is not a page number — is not."""
    return key == "#"


__all__ = [
    "BAND",
    "BAND_TOLERANCE",
    "REPEAT_RATIO",
    "SHORT_DOCUMENT_PAGES",
    "SHORT_DOCUMENT_REPEATS",
    "in_band",
    "key_of",
    "mark_furniture",
]
