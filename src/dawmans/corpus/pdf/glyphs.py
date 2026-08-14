"""Glyph detection and repair — requirements 5.1-5.5, stage 4 of the run.

The measured fault, from the APC Key 25 guide: its four Clip Stop arrows are set in
`Wingdings3`, embedded, Identity-H, **with** a ToUnicode CMap — and that CMap is the fault.
It maps the font's own codes 0x70/0x71/0x74/0x75 into the Latin-1 supplement (+0x80)
instead of to the glyphs, so the arrows extract as `ð, ñ, ô, õ`. Repair cannot come from
ToUnicode, because ToUnicode is what is wrong.

**Detection is font-keyed, not character-keyed.** A span is suspect when its font is a
symbol family and its characters are non-ASCII letters. Two halves, both load-bearing:

- The *font* test is the causal one. p14 of the same guide prints `contrôler` in the body
  face two lines from an arrow that extracts as `ô`; a character-keyed rule cannot repair
  the one without corrupting the other. There is no condition on neighbouring spans either
  — requiring ASCII neighbours only subtracts coverage, since an arrow inside a French
  sentence has non-ASCII neighbours.
- The *letter* test is what keeps an intact symbol intact. The same page sets its bullets
  in `Symbol`, which is a symbol family by name, and `•` came out of it correctly. A symbol
  font emitting a **letter** is the fault signature 5.1 describes; a symbol font emitting a
  symbol is a font doing its job.

Mapping, in order (design §Glyph repair):

1. **Embedded glyph names** — `embedded_names()`. `get_texttrace()` reports the raw glyph
   id beside the code point ToUnicode produced, `extract_font()` yields the font programme,
   and its `post` table names the glyph, which the Adobe Glyph List turns into a character.
   Be clear about the yield: most subsetters emit `post` v3.0, which carries no names, and
   the APC guide's Wingdings3 subset has no `post` table at all. For a novel symbol font
   the realistic outcome is `degraded` with 5.5 as the backstop — this path is not to be
   built up into something it cannot be.
2. **The corruption table** — `CORRUPTION_TABLE`, keyed on `(family, extracted code point)`.
   That is the code point the extractor returns *after* ToUnicode, so 0xF0/F1/F4/F5 for the
   APC arrows and **not** the published Wingdings 3 codes. It is a table of observed corrupt
   output for one font as one vendor shipped it, not a transcription of a character map.
3. **Unmappable.** The characters become U+FFFD, the span is marked `unmappable`, and the
   chunk carrying it is `degraded` (5.3). The raw characters never reach `Passage.text`, so
   BM25 cannot match them.

The 5.5 ratio's denominator is every character extracted from the text layer, counted
**after furniture suppression and before language selection**. Furniture is repeated
boilerplate that is never indexed and would dilute the ratio; language selection would make
the ratio depend on how much of the document is English, so a 2% arrow ratio in a
quarter-English guide would read as 8% and reject a good source. Over 2% is a rejection.

This module opens no PDF and imports no PyMuPDF. `embedded_names()` takes whatever
`extract.py` opened and calls three methods on it, which is what lets the wiring be tested
without a document.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from fontTools.agl import toUnicode
from fontTools.ttLib import TTFont, TTLibError

from dawmans.corpus.loader import Rejection
from dawmans.corpus.pdf.extract import Document, Span

#: Symbol families by name. A font in this set has no letters to emit, so a letter coming
#: out of one is a fault whatever it looks like.
SYMBOL_FAMILIES = frozenset(
    {
        "wingdings",
        "wingdings2",
        "wingdings3",
        "webdings",
        "symbol",
        "zapfdingbats",
        "dingbats",
    }
)

#: Observed corrupt output, per font family, for the ToUnicode CMap the vendor shipped.
#: The four APC Key 25 Clip Stop arrows: `Wingdings3` glyph ids 83, 84, 87 and 88, read off
#: the rendered page, are the solid triangles printed beside the buttons.
CORRUPTION_TABLE: dict[tuple[str, int], str] = {
    ("wingdings3", 0xF0): "▲",
    ("wingdings3", 0xF1): "▼",
    ("wingdings3", 0xF4): "◀",
    ("wingdings3", 0xF5): "▶",
}

#: 5.5's threshold, as a fraction of extracted characters.
UNMAPPABLE_LIMIT = 0.02

#: What an unmappable character is indexed as. Not the raw character (5.3) and not nothing:
#: dropping it silently would leave a plausible sentence with a word missing.
REPLACEMENT = "�"

_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")
_NON_FAMILY = re.compile(r"[^a-z0-9]")


def family_of(font: str) -> str:
    """`QZPXMI+Wingdings3` and `Wingdings 3` are one family: `wingdings3`.

    PDF subsetters prefix the six-letter tag; the space is how the same font is named in
    another producer's output.
    """
    return _NON_FAMILY.sub("", _SUBSET_PREFIX.sub("", font).casefold())


def symbol_families(fonts: Iterable[str]) -> frozenset[str]:
    """The caller's font names as family keys, normalised once rather than per span."""
    return frozenset(family_of(font) for font in fonts)


def is_symbol_font(font: str, symbol_fonts: Collection[str] = ()) -> bool:
    """A known family name, or a family the loader found to have no Latin coverage.

    The second arm is what makes detection work on a font nothing has heard of; reading a
    `cmap` needs the document, so the caller supplies the answer.
    """
    family = family_of(font)
    return family in SYMBOL_FAMILIES or family in symbol_families(symbol_fonts)


def is_suspect(character: str) -> bool:
    """A non-ASCII letter — the signature of a symbol mapped through a Latin encoding."""
    return character.isalpha() and not character.isascii()


@dataclass(frozen=True)
class GlyphAudit:
    """The 5.4 counts, which go into `index/audits/<slug>.json`."""

    glyph_spans_repaired: int = 0
    glyph_spans_degraded: int = 0
    unmappable_chars: int = 0
    extracted_chars: int = 0

    @property
    def unmappable_char_ratio(self) -> float:
        if not self.extracted_chars:
            return 0.0
        return self.unmappable_chars / self.extracted_chars

    @property
    def rejection(self) -> Rejection | None:
        """5.5: over the threshold the source is unreadable, not partly indexed."""
        if self.unmappable_char_ratio <= UNMAPPABLE_LIMIT:
            return None
        return Rejection(
            reason="unreadable-text",
            detail=(
                f"{self.unmappable_char_ratio:.1%} of extracted characters are unmappable, "
                f"over the {UNMAPPABLE_LIMIT:.0%} limit"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "glyph_spans_repaired": self.glyph_spans_repaired,
            "glyph_spans_degraded": self.glyph_spans_degraded,
            "unmappable_char_ratio": self.unmappable_char_ratio,
        }


def repair_document(
    document: Document,
    *,
    names: Mapping[tuple[str, int], str] | None = None,
    symbol_fonts: Collection[str] = (),
) -> GlyphAudit:
    """Repair `document` in place and return the 5.4 counts.

    `names` is path 1's mapping, from `embedded_names()`; where it holds an entry it wins,
    because a font programme naming its own glyph is better evidence than a table of what
    one vendor's output looked like.

    Repair runs over every span, furniture included — a marked line can be unmarked again by
    stage 5 or 7 — but the counts are taken over non-furniture text alone, which is what
    5.5's "after furniture suppression" means.
    """
    families = symbol_families(symbol_fonts)
    repaired = degraded = unmappable = counted = 0
    for page in document.pages:
        for line in page.lines:
            for span in line.spans:
                span.text, repairs = _repair_span(span, names or {}, families)
                unreadable = span.text.count(REPLACEMENT)
                if unreadable:
                    span.unmappable = True
                if line.furniture:
                    continue
                counted += len(span.text)
                unmappable += unreadable
                degraded += 1 if unreadable else 0
                repaired += 1 if repairs else 0

    return GlyphAudit(
        glyph_spans_repaired=repaired,
        glyph_spans_degraded=degraded,
        unmappable_chars=unmappable,
        extracted_chars=counted,
    )


def _repair_span(
    span: Span, names: Mapping[tuple[str, int], str], families: Collection[str]
) -> tuple[str, int]:
    """The mapped text of one span, and how many of its characters were repaired.

    A span can be both repaired and degraded — one arrow in the table, the next not — so
    the two are counted separately rather than as one verdict.
    """
    family = family_of(span.font)
    if family not in SYMBOL_FAMILIES and family not in families:
        return span.text, 0
    if not any(is_suspect(character) for character in span.text):
        return span.text, 0

    out: list[str] = []
    repaired = 0
    for character in span.text:
        if not is_suspect(character):
            out.append(character)
            continue
        key = (family, ord(character))
        mapped = names.get(key) or CORRUPTION_TABLE.get(key)
        out.append(mapped or REPLACEMENT)
        repaired += 1 if mapped else 0
    return "".join(out), repaired


# --- Path 1: the embedded font programme ------------------------------------------------


def name_to_character(name: str) -> str | None:
    """A glyph name through the Adobe Glyph List: `arrowright` and `uni2192` both give →."""
    if not name:
        return None
    return toUnicode(name) or None


def glyph_names(programme: bytes) -> dict[int, str]:
    """Glyph id to glyph name, from a font programme's `post` table.

    Only format 2.0 carries names. Anything else — v3.0, which is what most subsetters
    emit, or no `post` table at all, which is what the APC guide's Wingdings3 subset has —
    yields nothing, and so does anything that is not a font: a programme that will not
    parse is a repair that cannot happen, not a run that should fail. fontTools will invent
    an order from the `cmap` when asked, and those names are not evidence of anything.
    """
    try:
        font = TTFont(BytesIO(programme), fontNumber=0, lazy=True)
        if "post" not in font or font["post"].formatType != 2.0:
            return {}
        order = font.getGlyphOrder()
    except (TTLibError, OSError, ValueError, KeyError, IndexError, AssertionError):
        return {}
    return dict(enumerate(order))


def document_symbol_families(
    document: Document, symbol_fonts: Collection[str] = ()
) -> frozenset[str]:
    """The symbol families the extracted span model actually holds.

    This is what says whether path 1 has anything to look for, and it is answered from the
    span model rather than from the PDF because the span model is already in memory.
    """
    known = symbol_families(symbol_fonts)
    return frozenset(
        family
        for family in (family_of(span.font) for span in document.spans)
        if family in SYMBOL_FAMILIES or family in known
    )


def embedded_names(doc: Any, families: Collection[str] = ()) -> dict[tuple[str, int], str]:
    """`(family, extracted code point) -> character`, read from the embedded programmes.

    `doc` is whatever `extract.py` opened; the three calls made on it are `get_fonts`,
    `get_texttrace` and `extract_font`. `families` is `document_symbol_families()` of the
    same document, and it is not an optimisation to pass it: measured, walking the page
    resources of Live 12's 1009 pages to discover there is no symbol font costs 5.2 s
    against a 60 s budget for the whole rebuild, and the span model already knows. An empty
    set opens no page at all.
    """
    wanted = symbol_families(families)
    if not wanted:
        return {}

    programmes: dict[str, dict[int, str]] = {}
    mapping: dict[tuple[str, int], str] = {}

    for page in doc:
        families_here = _symbol_fonts_on(page, wanted)
        if not families_here:
            continue
        for family, xref in families_here.items():
            if family not in programmes:
                programmes[family] = glyph_names(_programme(doc, xref))
        for item in page.get_texttrace():
            family = family_of(item.get("font", ""))
            names = programmes.get(family)
            if not names:
                continue
            for char in item.get("chars", ()):
                character = name_to_character(names.get(char[1], ""))
                if character:
                    mapping[(family, char[0])] = character
    return mapping


def _symbol_fonts_on(page: Any, wanted: Collection[str]) -> dict[str, int]:
    """The wanted families this page draws with, and the xref of each one's programme."""
    found: dict[str, int] = {}
    for entry in page.get_fonts(full=True):
        xref, basefont = entry[0], entry[3]
        family = family_of(basefont)
        if family in wanted:
            found.setdefault(family, xref)
    return found


def _programme(doc: Any, xref: int) -> bytes:
    """The embedded font's bytes. An unembedded font yields none, and that is not an
    error: it is a font the reader is expected to have, which cannot be a subset fault."""
    try:
        extracted: Iterable[Any] = doc.extract_font(xref)
    except (RuntimeError, ValueError):
        return b""
    parts = list(extracted)
    return parts[3] if len(parts) > 3 and isinstance(parts[3], bytes) else b""


__all__ = [
    "CORRUPTION_TABLE",
    "REPLACEMENT",
    "SYMBOL_FAMILIES",
    "UNMAPPABLE_LIMIT",
    "GlyphAudit",
    "document_symbol_families",
    "embedded_names",
    "family_of",
    "glyph_names",
    "is_suspect",
    "is_symbol_font",
    "name_to_character",
    "repair_document",
    "symbol_families",
]
