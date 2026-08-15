"""The committed extraction snapshots of `tests/fixtures/` — requirement 3.1, task 11.

`manuals/` is gitignored, so no test may open a reference PDF. The vendor guides enter the
suite here instead, as snapshots of what `corpus/pdf/extract.py` returned for a named page
range, captured by `tools/capture_fixture.py` and recaptured with `make fixtures`. That
makes the extractor's output an explicit input to every downstream stage: a change to
extraction lands as a diff in these files rather than as a surprise in a chunking test.

What is asserted here is that each fixture still holds the thing it was captured for. The
stages that consume them do not exist yet — furniture, glyphs, language, sectioning and
layout are phases 4 and 5 — and a fixture that has quietly lost its arrows or its ragged
table would otherwise be discovered by a failing test in whichever of those got there
first, months from the capture.

The reference guides are copyrighted and the fixtures are the one place their text enters
the repository, so the redaction of `apc_pages` is asserted here too: no word of the guide
survives it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import capture_fixture
import pytest

from conftest import FIXTURE_DIR
from dawmans.corpus.discover import parse_filename
from dawmans.corpus.pdf.extract import SNAPSHOT_SCHEMA, Document

FIXTURE_NAMES = [fixture.name for fixture in capture_fixture.FIXTURES]
REJECTION_NAMES = ["image_only", "unreadable_text", "filenames"]


def read(name: str) -> dict:
    path = FIXTURE_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load(name: str) -> Document:
    return Document.from_dict(read(name))


def spans(document: Document) -> list:
    return document.spans


# --- The set itself ---------------------------------------------------------------------


def test_every_declared_fixture_is_committed() -> None:
    """The capture list is the record of which pages of which guide each fixture is."""
    committed = {path.stem for path in FIXTURE_DIR.glob("*.json")}
    assert committed == set(FIXTURE_NAMES)


def test_every_rejection_fixture_is_committed() -> None:
    committed = {path.stem for path in (FIXTURE_DIR / "rejections").glob("*.json")}
    assert committed == set(REJECTION_NAMES)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_a_fixture_loads_and_says_what_it_is_for(name: str) -> None:
    raw = read(name)
    assert raw["schema"] == SNAPSHOT_SCHEMA
    assert raw["captured_from"].endswith(".pdf")
    assert raw["asserts"]

    document = load(name)
    assert [page.number for page in document.pages] == raw["captured_pages"]
    assert document.page_count >= len(document.pages)
    assert all(page.number <= document.page_count for page in document.pages)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_a_fixture_round_trips_through_the_snapshot_form(name: str) -> None:
    """The fixtures are read back through the same code that wrote them, so a change to
    either half shows up here rather than as a silently different span model."""
    document = load(name)
    assert Document.from_dict(document.to_dict()) == document


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_a_fixture_carries_geometry_and_no_image_bytes(name: str) -> None:
    document = load(name)
    for page in document.pages:
        assert page.width > 0 and page.height > 0
        for rect in page.images:  # placements only — 10.1
            assert len(rect) == 4
        for span in spans(document):
            x0, y0, x1, y1 = span.bbox
            assert x1 >= x0 and y1 >= y0
            assert span.font


# --- What each fixture was captured for -------------------------------------------------


def test_nitro_max_p25_holds_the_ragged_trigger_table() -> None:
    """7.1-7.3, 7.6: two panels, 11 rows left and 8 right, all 19 pairs printed."""
    page = load("nitro_max_p25").pages[0]
    text = page.text

    for trigger, note in (("Kick", "36"), ("Snare", "38"), ("Ride", "51"), ("HH Splash", "21")):
        assert trigger in text and note in text
    printed = [line.text.strip() for line in page.lines]
    assert printed.count("MIDI Note") == 2  # the heading repeats across the two panels
    assert printed.count("Number") == 2  # its third physical line, which a naive read loses


def test_apc_p14_holds_one_code_point_in_two_fonts() -> None:
    """5.1-5.2: detection is font-keyed, not character-keyed.

    U+00F4 is on this page twice — as a Wingdings3 arrow and inside a French word set in
    the body face. A character-keyed rule cannot repair the first without corrupting the
    second, which is the whole reason the font test exists.
    """
    page = load("apc_p14_arrows").pages[0]
    symbol = [span for span in page.spans if span.font.endswith("Wingdings3")]
    body = [span for span in page.spans if not span.font.endswith("Wingdings3")]

    assert "".join(span.text for span in symbol) == "ðñôõ"
    assert any("ô" in span.text for span in body)


def test_apc_pages_is_redacted_and_labelled() -> None:
    """4.2-4.6 drive off the label; the text is masked because 24 pages of it would
    commit substantially the whole guide."""
    raw = read("apc_pages")
    assert raw["redacted"] is True

    document = load("apc_pages")
    assert document.page_count == 24
    assert len(document.pages) == 24

    for span in document.spans:
        assert all(character in "xX" for character in span.text if character.isalpha())
        assert all(character == "0" for character in span.text if character.isdigit())

    labels = {
        page.number: {block.lang for block in page.blocks if block.lang} for page in document.pages
    }
    assert labels[3] == labels[4] == labels[5] == labels[6] == {"en"}
    assert labels[23] == {"en"}
    assert labels[8] == {"es"}
    assert labels[14] == {"fr"}
    assert labels[20] == {"de"}
    assert labels[1] == {"en", "es", "fr", "it", "de"}  # the printed language index


def test_apc_pages_keeps_the_shape_the_language_stage_measures() -> None:
    """Masking rather than dropping the text is what makes the fixture usable: the short
    block guard (under 8 words) and the language-neutral guard (predominantly
    non-alphabetic tokens) both measure shape, and shape is all that survives."""
    document = load("apc_pages")
    words = [block.word_count for page in document.pages for block in page.blocks]

    assert any(count < 8 for count in words)  # headings and table cells
    assert any(count >= 8 for count in words)  # prose the detector would score


def test_live_toc_slice_carries_the_outline_and_its_parent_chain() -> None:
    """6.3, 6.6: 'Sidechain Parameters' occurs eight times in Live's outline, so the
    ancestor titles are the only thing that tells one of them from another."""
    document = load("live_toc_slice")
    titles = [entry.title for entry in document.toc]

    assert "28.21 Glue Compressor" in titles
    assert "28.21.1 Sidechain Parameters" in titles
    glue = next(entry for entry in document.toc if entry.title == "28.21 Glue Compressor")
    sidechain = next(
        entry for entry in document.toc if entry.title == "28.21.1 Sidechain Parameters"
    )
    assert sidechain.level == glue.level + 1
    assert sidechain.page >= glue.page

    numbers = [page.number for page in document.pages]
    assert 471 in numbers  # the 23/24 chapter boundary
    assert {586, 587, 588} <= set(numbers)

    on_one_page = [entry for entry in document.toc if entry.page == 471]
    assert len(on_one_page) > 1  # two sections sharing a page, which is the anchoring case


def test_live_contents_p13_is_a_printed_contents_page() -> None:
    """6.5: it contributes no chunks. Live prints its page numbers as a separate
    right-hand column of bare numerals rather than behind dot leaders, so the detector
    that has to catch this page cannot be the dot-leader test alone."""
    page = load("live_contents_p13").pages[0]
    stripped = [line.text.strip() for line in page.lines if line.text.strip()]
    numerals = [line for line in stripped if line.isdigit()]

    assert len(numerals) > len(stripped) / 3
    assert not any("...." in line for line in stripped)
    right_column = [line for line in page.lines if line.text.strip().isdigit()]
    assert all(line.bbox[0] > page.width * 0.8 for line in right_column)


def test_live_procedure_pagebreak_spans_two_pages() -> None:
    """6.10 and 6.8: steps 1-4 on p158, step 5 on p159, one procedure.

    The enumerators are set in a left gutter and extract after the step text they belong
    to, so a chunker reading extraction order alone gets the steps and the numbers in
    separate runs. Only row assembly on geometry puts them back.
    """
    first, second = load("live_procedure_pagebreak").pages
    assert (first.number, second.number) == (158, 159)

    enumerators = [
        line.text.strip() for line in first.lines if re.fullmatch(r"\d+\.", line.text.strip())
    ]
    assert enumerators == ["1.", "2.", "3.", "4."]
    assert "5." in [line.text.strip() for line in second.lines]
    assert "When searching is complete" in second.text


def test_apc_no_toc_withholds_the_outline() -> None:
    """6.4: the heading-style path, which needs a document with no outline. Every manual
    in the reference corpus has one, so this fixture is captured without it — see
    decision_log.md Decision 10."""
    document = load("apc_no_toc")
    assert document.toc == []

    sizes = {span.size for span in document.spans}
    assert len(sizes) > 1  # headings are set larger than the body, which path C keys on


def test_cover_only_is_a_title_and_a_strapline() -> None:
    """6.5: path C's quality gate has to fail here, or a cover alone yields two bogus
    regions spanning the whole document."""
    document = load("cover_only")
    page = document.pages[0]
    printed = [line.text.strip() for line in page.lines if line.text.strip()]

    assert printed[0] == "Ableton Live 12 Manual"
    assert printed[1] == "for Windows and Mac"
    assert len(document.pages) == 1
    assert document.page_count == 1009  # one page of a very long document


def test_furniture_pages_repeat_a_page_number_in_the_band() -> None:
    """3.6: the digits-only rule is the one that does the work on this corpus."""
    document = load("furniture_pages")
    assert [page.number for page in document.pages] == [23, 24, 25, 26]

    for page in document.pages:
        band = [
            line.text.strip()
            for line in page.lines
            if line.bbox[1] < page.height * 0.08 or line.bbox[3] > page.height * 0.92
        ]
        assert str(page.number) in band


# --- The rejection fixtures -------------------------------------------------------------


def test_image_only_has_no_text_layer() -> None:
    """3.3: zero non-furniture spans across every page."""
    document = Document.from_dict(read("rejections/image_only"))

    assert document.pages
    assert document.spans == []
    assert document.has_text_layer is False
    assert all(page.images for page in document.pages)


def test_unreadable_text_is_over_the_two_percent_threshold() -> None:
    """5.5: the denominator is every character extracted from the text layer."""
    document = Document.from_dict(read("rejections/unreadable_text"))

    characters = sum(len(span.text) for span in document.spans)
    unmappable = sum(len(span.text) for span in document.spans if span.font == "Wingdings3")
    assert unmappable / characters > capture_fixture.UNMAPPABLE_LIMIT
    assert document.has_text_layer is True  # it has text; the text is unreadable


def test_the_filename_rejection_cases_are_still_rejected() -> None:
    """2.5 and 2.6, pinned against the grammar itself rather than restated in prose."""
    cases = read("rejections/filenames")

    for name in cases["filename_invalid"]:
        assert parse_filename(name) is None, name

    identities = [parse_filename(name) for name in cases["collision"]]
    assert all(identity is not None for identity in identities)
    assert len({identity.source_id for identity in identities}) == 1


# --- The capture tool -------------------------------------------------------------------


def test_the_page_spec_takes_ranges_and_lists() -> None:
    assert capture_fixture.parse_pages("25") == [25]
    assert capture_fixture.parse_pages("3-6") == [3, 4, 5, 6]
    assert capture_fixture.parse_pages("470-471,584-585") == [470, 471, 584, 585]


def test_the_label_spec_takes_page_ranges_and_single_blocks() -> None:
    labels = capture_fixture.parse_labels("3-4=en,7=es,1.3=fr")
    assert labels[(3, None)] == "en"
    assert labels[(4, None)] == "en"
    assert labels[(7, None)] == "es"
    assert labels[(1, 3)] == "fr"


def test_redaction_masks_every_letter_in_every_script() -> None:
    """`[a-zA-Z]` would leave the accented characters standing, and on a multilingual
    guide those are exactly what identifies the language of the line they are in."""
    masked = capture_fixture.mask("Contrôle Español 8x5 — (23)")

    assert masked == "Xxxxxxxx Xxxxxxx 0x0 — (00)"
    assert not any(character.isalpha() and character not in "xX" for character in masked)


def test_redaction_keeps_the_measurable_shape() -> None:
    original = "Press the button 3 times. Then wait."
    masked = capture_fixture.mask(original)

    assert len(masked) == len(original)
    assert len(masked.split()) == len(original.split())
    assert masked.count(".") == original.count(".")


def test_a_snapshot_of_an_unknown_schema_is_refused() -> None:
    with pytest.raises(ValueError, match="snapshot schema"):
        Document.from_dict({"schema": "something-else", "page_count": 1, "pages": []})


def test_the_fixtures_stay_small_enough_to_review() -> None:
    """A fixture is committed source: one that has grown into a megabyte is a capture
    that took more of a copyrighted guide than it needed."""
    for path in Path(FIXTURE_DIR).rglob("*.json"):
        assert path.stat().st_size < 1_000_000, path.name
