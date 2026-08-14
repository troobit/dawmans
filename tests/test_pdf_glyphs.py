"""Glyph detection and repair — requirements 5.1-5.5, stage 4.

The measured case: the APC Key 25 guide sets its four Clip Stop arrows in `Wingdings3`,
embedded, Identity-H, **with** a ToUnicode CMap that maps the font's own codes 0x70/71/74/75
into the Latin-1 supplement instead of to the glyphs. They extract as `ð, ñ, ô, õ`. Repair
therefore cannot come from ToUnicode, and it cannot come from the characters either: p14 of
the same guide prints a genuine French `ô` in the body face two lines away, so a
character-keyed rule that repairs the arrow corrupts the word. Detection is font-keyed, and
that is what these tests pin.

The fixture is `apc_p14_arrows` rather than the design's `apc_p3_arrows`: p3 of v1.0 carries
no symbol font, and p14 is the stronger case because U+00F4 is on it twice, once in each
font (see `tools/capture_fixture.py`).
"""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from conftest import FIXTURE_DIR
from dawmans.corpus.pdf.extract import Document, Span
from dawmans.corpus.pdf.furniture import mark_furniture
from dawmans.corpus.pdf.glyphs import (
    CORRUPTION_TABLE,
    REPLACEMENT,
    UNMAPPABLE_LIMIT,
    document_symbol_families,
    embedded_names,
    family_of,
    glyph_names,
    is_symbol_font,
    name_to_character,
    repair_document,
)
from spanmodel import SYMBOL, block_of, document_of, footer, line_of, page_of, span, text_line

#: What the four APC arrows are printed as, read off the rendered glyphs of p14.
ARROWS = "▲▼◀▶"

PROSE = "Connect the interface and set the input gain until the meter stays green. "


def fixture(name: str) -> Document:
    raw = (FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")
    return Document.from_dict(json.loads(raw))


def symbol_document(symbols: str, *, pages: int = 1, prose: int = 1) -> Document:
    """One symbol run on page 1, with `prose` lines of body text on each of `pages`."""
    return document_of(
        *(
            page_of(
                number,
                block_of(
                    *(text_line(PROSE, top=100.0 + index * 13.2) for index in range(prose)),
                    *(
                        [line_of([span(symbols, font=SYMBOL, top=300.0, width=30.0)])]
                        if number == 1
                        else []
                    ),
                ),
            )
            for number in range(1, pages + 1)
        )
    )


# --- Detection is font-keyed (5.1) ----------------------------------------------------------


def test_the_apc_arrows_repair_to_the_glyphs_that_are_printed() -> None:
    """5.2, against the fixture. The characters are pinned here rather than described:
    a wrong corruption-table entry is otherwise a silent mistranslation that reaches a
    user as a confident quotation."""
    document = fixture("apc_p14_arrows")
    audit = repair_document(document)

    symbols = [span for span in document.spans if span.font.endswith(SYMBOL)]
    assert "".join(span.text for span in symbols) == ARROWS
    assert audit.glyph_spans_repaired == 4
    assert audit.glyph_spans_degraded == 0


def test_the_same_code_point_in_the_body_face_is_left_alone() -> None:
    """U+00F4 is on p14 twice: as a Wingdings3 arrow and inside a French word set in
    HelveticaNeue-Roman. Only the font test tells them apart."""
    document = fixture("apc_p14_arrows")
    before = [span.text for span in document.spans if span.font.endswith("HelveticaNeue-Roman")]
    assert any("ô" in text for text in before)

    repair_document(document)

    after = [span.text for span in document.spans if span.font.endswith("HelveticaNeue-Roman")]
    assert after == before
    assert "contrôler" in document.pages[0].text


def test_a_bullet_set_in_a_symbol_font_is_not_a_fault() -> None:
    """The same page sets its bullets in `Symbol`, a symbol family by name. `•` is a
    symbol that arrived intact, so it is neither repaired nor degraded — the fault
    signature is a *letter* coming out of a font that has none."""
    document = fixture("apc_p14_arrows")
    audit = repair_document(document)

    bullets = [span for span in document.spans if span.font.endswith("Symbol")]
    assert bullets and all(span.text.strip() == "•" for span in bullets)
    assert not any(span.unmappable for span in bullets)
    assert audit.unmappable_chars == 0


def test_a_symbol_family_is_recognised_through_its_subset_prefix() -> None:
    assert family_of("QZPXMI+Wingdings3") == "wingdings3"
    assert family_of("Wingdings 3") == "wingdings3"
    assert is_symbol_font("QZPXMI+Wingdings3")
    assert is_symbol_font("ZapfDingbats")
    assert not is_symbol_font("WWFPLX+HelveticaNeue-Roman")


def test_a_font_the_loader_found_to_have_no_latin_coverage_is_a_symbol_font() -> None:
    """The second arm of the detection test. A novel symbol font has a name nothing knows,
    so the loader passes in what it read from the font's own cmap."""
    assert not is_symbol_font("Nova-Icons")
    assert is_symbol_font("ABCDEF+Nova-Icons", symbol_fonts={"nova-icons"})


# --- The corruption table (5.2) --------------------------------------------------------------


def test_the_table_is_keyed_on_the_code_point_the_extractor_returns() -> None:
    """0xF0/F1/F4/F5 — after ToUnicode — and not the published Wingdings 3 codes
    0x70/71/74/75. It is a table of observed corrupt output, not a character map."""
    keys = {code for family, code in CORRUPTION_TABLE if family == "wingdings3"}

    assert keys == {0xF0, 0xF1, 0xF4, 0xF5}
    assert not keys & {0x70, 0x71, 0x74, 0x75}
    assert [CORRUPTION_TABLE[("wingdings3", code)] for code in (0xF0, 0xF1, 0xF4, 0xF5)] == list(
        ARROWS
    )


# --- Unmappable (5.3) --------------------------------------------------------------------------


def test_an_unmapped_symbol_span_is_degraded_and_never_indexed_as_words() -> None:
    """5.3: the containing chunk carries `degraded` and the raw characters do not reach
    the text, so BM25 cannot match them."""
    document = symbol_document("ÐÑÒÓ")
    audit = repair_document(document)

    symbols = [span for span in document.spans if span.font == SYMBOL]
    assert [span.text for span in symbols] == [REPLACEMENT * 4]
    assert all(span.unmappable for span in symbols)
    assert audit.glyph_spans_degraded == 1
    assert audit.glyph_spans_repaired == 0

    text = document.pages[0].text
    assert not any(character in text for character in "ÐÑÒÓ")
    assert not any(REPLACEMENT in word.strip(REPLACEMENT) for word in text.split())


def test_a_span_of_mixed_luck_repairs_what_it_can_and_degrades_the_rest() -> None:
    document = symbol_document("ð?Ð")
    audit = repair_document(document)

    symbol = next(span for span in document.spans if span.font == SYMBOL)
    assert symbol.text == f"▲?{REPLACEMENT}"
    assert symbol.unmappable
    assert (audit.glyph_spans_repaired, audit.glyph_spans_degraded) == (1, 1)


# --- The 5.5 ratio and its denominator ----------------------------------------------------------


def test_the_denominator_is_every_extracted_character_not_the_english_part() -> None:
    """5.5's denominator is counted before language selection. A 2% arrow ratio in a
    quarter-English guide would read as 8% if only the English pages were counted, and the
    source would be rejected for being multilingual."""
    symbols = "ÐÑÒÓÐÑÒÓ"
    document = symbol_document(symbols, pages=4, prose=2)
    audit = repair_document(document)

    english_only = len(symbols) / (2 * len(PROSE) + len(symbols))
    assert audit.unmappable_char_ratio < UNMAPPABLE_LIMIT < english_only
    assert audit.rejection is None


def test_the_denominator_excludes_suppressed_furniture() -> None:
    """Counted after furniture suppression: repeated boilerplate is never indexed, and
    counting it would dilute the ratio of the text that is."""

    def build() -> Document:
        document = symbol_document("ÐÑÒÓ", pages=6, prose=6)
        for page in document.pages:
            page.blocks.append(footer(str(page.number)))
            page.blocks.append(footer(PROSE * 2, x0=40.0))  # a running footer, and a long one
        return document

    loose = repair_document(build()).unmappable_char_ratio
    suppressed = build()
    mark_furniture(suppressed)
    tight = repair_document(suppressed).unmappable_char_ratio

    assert tight > loose


def test_over_the_threshold_is_the_unreadable_text_rejection() -> None:
    """5.5 against the synthetic fixture, which is over 2% on purpose."""
    document = fixture("rejections/unreadable_text")
    audit = repair_document(document)

    assert audit.unmappable_char_ratio > UNMAPPABLE_LIMIT
    assert audit.rejection is not None
    assert audit.rejection.reason == "unreadable-text"
    assert f"{audit.unmappable_char_ratio:.1%}" in audit.rejection.detail


def test_a_clean_document_is_neither_repaired_nor_rejected() -> None:
    document = symbol_document("", pages=2, prose=4)
    audit = repair_document(document)

    assert audit.unmappable_char_ratio == 0.0
    assert audit.rejection is None


def test_the_audit_carries_the_counts_the_source_report_needs() -> None:
    """5.4: repaired and degraded spans, plus the ratio, reach `index/audits/<slug>.json`."""
    document = fixture("apc_p14_arrows")
    audit = repair_document(document).to_dict()

    assert set(audit) == {
        "glyph_spans_repaired",
        "glyph_spans_degraded",
        "unmappable_char_ratio",
    }
    assert audit["glyph_spans_repaired"] == 4
    assert audit["unmappable_char_ratio"] == 0.0


# --- Path 1: embedded glyph names -------------------------------------------------------


def font_bytes(names: dict[int, str], *, post: bool = True) -> bytes:
    """A font programme whose `post` table names the glyphs, as an unsubsetted font does."""
    order = [".notdef"] + [names[gid] for gid in sorted(names)]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({0x41 + index: name for index, name in enumerate(order[1:])})
    builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in order})
    builder.setupHorizontalMetrics({name: (500, 0) for name in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Nova Icons", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost(keepGlyphNames=post)
    buffer = BytesIO()
    builder.save(buffer)
    return buffer.getvalue()


def test_a_glyph_name_resolves_through_the_adobe_glyph_list() -> None:
    assert name_to_character("arrowright") == "→"
    assert name_to_character("uni2192") == "→"
    assert name_to_character("notaglyphname") is None
    assert name_to_character("") is None


def test_the_post_table_gives_a_name_per_glyph_id() -> None:
    assert glyph_names(font_bytes({1: "arrowright", 2: "arrowleft"})) == {
        0: ".notdef",
        1: "arrowright",
        2: "arrowleft",
    }


def test_a_subsetted_font_with_no_glyph_names_yields_none() -> None:
    """The realistic outcome, and the reason 5.5 is the backstop: most subsetters emit
    `post` v3.0, which carries no names at all. The APC guide's Wingdings3 subset has no
    `post` table whatsoever."""
    assert glyph_names(font_bytes({1: "arrowright"}, post=False)) == {}
    assert glyph_names(b"not a font at all") == {}


class FakePage:
    """The three PyMuPDF calls path 1 makes, and nothing else."""

    def __init__(self, fonts: list[tuple], trace: list[dict]) -> None:
        self._fonts, self._trace = fonts, trace

    def get_fonts(self, full: bool = False) -> list[tuple]:
        return self._fonts

    def get_texttrace(self) -> list[dict]:
        return self._trace


class FakeDocument:
    def __init__(self, pages: list[FakePage], programmes: dict[int, bytes]) -> None:
        self._pages, self._programmes = pages, programmes

    def __iter__(self):
        return iter(self._pages)

    def extract_font(self, xref: int) -> tuple:
        return ("ABCDEF+NovaIcons", "ttf", "Type0", self._programmes[xref])


def test_embedded_names_relates_the_extracted_code_point_to_the_glyph_it_drew() -> None:
    """ToUnicode is the fault, so the code point the extractor returned is useless on its
    own; `get_texttrace` reports the raw glyph id beside it, and the font programme names
    that glyph."""
    page = FakePage(
        fonts=[(7, "ttf", "Type0", "ABCDEF+NovaIcons", "R1", "Identity-H", 0)],
        trace=[{"font": "ABCDEF+NovaIcons", "chars": [(0x00F0, 1, (0, 0), (0, 0, 1, 1))]}],
    )
    doc = FakeDocument([page], {7: font_bytes({1: "arrowright"})})

    assert embedded_names(doc, {"Nova-Icons"}) == {("novaicons", 0x00F0): "→"}


def test_a_document_with_no_symbol_font_is_never_opened() -> None:
    """Measured: walking the page resources of Live 12's 1009 pages to find out there is
    no symbol font costs 5.2 s of a 60 s rebuild. The span model already knows, so the
    families it holds are what decides whether the PDF is read again at all."""

    class Tripwire(FakePage):
        def get_fonts(self, full: bool = False) -> list[tuple]:
            raise AssertionError("opened a page of a document with no symbol font")

    assert embedded_names(FakeDocument([Tripwire([], [])], {}), ()) == {}


def test_the_families_come_from_the_span_model() -> None:
    document = symbol_document("ð", pages=2, prose=2)

    prose_only = document_of(page_of(1, block_of(text_line("Set the gain.", top=100.0))))

    assert document_symbol_families(document) == frozenset({"wingdings3"})
    assert document_symbol_families(prose_only) == frozenset()


def test_an_embedded_name_beats_the_corruption_table() -> None:
    """The table is observed output for a font whose programme could not be read; where
    the programme can be read, it is the better evidence."""
    document = symbol_document("ð")
    audit = repair_document(document, names={("wingdings3", 0xF0): "→"})

    assert next(span for span in document.spans if span.font == SYMBOL).text == "→"
    assert audit.glyph_spans_repaired == 1


@pytest.mark.parametrize("character", ["A", "3", " ", "•", "→"])
def test_only_a_non_ascii_letter_is_a_fault(character: str) -> None:
    """A symbol font emitting a letter is the fault signature; anything else that comes
    out of one is a symbol that survived, and repairing it would be the corruption."""
    document = document_of(
        page_of(
            1,
            block_of(
                line_of(
                    [Span(text=character, bbox=(72.0, 100.0, 90.0, 110.0), font=SYMBOL, size=10.0)]
                )
            ),
        )
    )
    audit = repair_document(document)

    assert document.pages[0].text == character
    assert (audit.glyph_spans_repaired, audit.glyph_spans_degraded) == (0, 0)
