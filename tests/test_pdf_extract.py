"""PDF extraction and the span model — requirements 3.1-3.5, 10.1, 10.2, 10.4.

The load-bearing test here is the image one. PyMuPDF's default dict flags materialise
every image's bytes into a type-1 block, so extracting Live 12 with the defaults reads
96 MB of screenshots into memory: 10.1 says image content is not extracted and 10.4 says
the screenshots cost file size and nothing else, and clearing `TEXT_PRESERVE_IMAGES` is
what makes both hold at once. It is asserted here as a property of the output — the same
text model from a page with and without a screenshot on it — rather than as a flag value,
because the flag is the mechanism and the model is the requirement.

`manuals/` is gitignored and no test may open a reference PDF, so these build their own
PDFs with `tests/pdfgen.py`. The reference guides enter the suite as the committed
extraction snapshots of `tests/fixtures/`, which is `test_pdf_fixtures.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dawmans.corpus.pdf.extract import (
    EXTRACT_FLAGS,
    LOW_TEXT_WORDS_PER_PAGE,
    PRESERVE_IMAGES,
    extract_document,
)
from pdfgen import HELVETICA, HELVETICA_BOLD, Image, Page, Text, lines, write_pdf

PROSE = (
    "The tempo control sets the speed of the transport in beats per minute, "
    "and the value is shown in the control bar at the top of the window."
)


def build(tmp_path: Path, pages: list[Page], name: str = "vendor_product_guide_v1_en.pdf") -> Path:
    return write_pdf(tmp_path / name, pages)


def prose_page(word_target: int, top: float = 100.0) -> Page:
    """A page of ordinary prose holding roughly `word_target` words."""
    source = PROSE.split()
    words = [source[index % len(source)] for index in range(word_target)]
    body = [" ".join(words[i : i + 12]) for i in range(0, word_target, 12)]
    return Page(texts=lines(*body, top=top))


# --- Images: 10.1, 10.4 -----------------------------------------------------------------


def test_image_content_never_reaches_the_span_model(tmp_path: Path) -> None:
    """10.1: a text-only index. An image contributes a rectangle and nothing else."""
    path = build(
        tmp_path,
        [
            Page(
                texts=lines("Figure 3. The Session View mixer.", top=560),
                images=(Image(72.0, 200.0, 400.0, 300.0, resolution=128),),
            )
        ],
    )

    document = extract_document(path)
    page = document.pages[0]

    assert [span.text for span in page.spans] == ["Figure 3. The Session View mixer."]
    assert page.images == [(72.0, 200.0, 472.0, 500.0)]

    # The snapshot is the committed fixture form, so "no image key carrying bytes" is
    # asserted where it would otherwise be committed to the repository.
    snapshot = json.dumps(document.to_dict())
    assert "image" not in {key for key in _keys(document.to_dict()) if key != "images"}
    assert len(snapshot) < path.stat().st_size / 10


def test_a_screenshot_costs_file_size_and_nothing_else(tmp_path: Path) -> None:
    """10.4: the 96 MB of screenshots in Live 12 have no effect other than file size."""
    texts = lines("Recording a session", "1. Arm the track.", "2. Press Record.", top=100)
    plain = build(tmp_path, [Page(texts=texts)], "plain_guide_manual_v1_en.pdf")
    dense = build(
        tmp_path,
        [Page(texts=texts, images=(Image(72.0, 300.0, 468.0, 400.0, resolution=512),))],
        "dense_guide_manual_v1_en.pdf",
    )

    assert dense.stat().st_size > plain.stat().st_size * 100

    plain_pages = extract_document(plain).to_dict()["pages"]
    dense_pages = extract_document(dense).to_dict()["pages"]
    for page in (*plain_pages, *dense_pages):
        page.pop("images")
    assert dense_pages == plain_pages


def test_the_extraction_flags_clear_preserve_images() -> None:
    """The mechanism behind the two tests above, stated once so a change to it is loud."""
    assert EXTRACT_FLAGS & PRESERVE_IMAGES == 0


def test_figure_captions_are_indexed_as_ordinary_text(tmp_path: Path) -> None:
    """10.2: a caption in the text layer is text, not something skipped near an image."""
    path = build(
        tmp_path,
        [
            Page(
                texts=(
                    Text("Figure 12. The Nitro Max trigger layout.", 72.0, 520.0),
                    *lines("Each pad sends the note number listed in the table.", top=560),
                ),
                images=(Image(72.0, 200.0, 400.0, 300.0, resolution=64),),
            )
        ],
    )

    text = extract_document(path).pages[0].text
    assert "Figure 12. The Nitro Max trigger layout." in text
    assert "Each pad sends the note number listed in the table." in text


# --- No text layer: 3.3 -----------------------------------------------------------------


def test_a_source_with_no_text_layer_is_detected(tmp_path: Path) -> None:
    """3.3: zero non-furniture spans across every page is the `no-text-layer` rejection."""
    scanned = build(
        tmp_path,
        [
            Page(images=(Image(0.0, 0.0, 612.0, 792.0, resolution=256),)),
            Page(images=(Image(0.0, 0.0, 612.0, 792.0, resolution=256),)),
        ],
    )

    document = extract_document(scanned)
    assert document.page_count == 2
    assert document.spans == []
    assert document.has_text_layer is False


def test_whitespace_is_not_a_text_layer(tmp_path: Path) -> None:
    path = build(tmp_path, [Page(texts=lines("   ", "\t", top=100))])

    assert extract_document(path).has_text_layer is False


def test_a_stamped_page_number_is_not_a_text_layer(tmp_path: Path) -> None:
    """3.3 counts **non-furniture** spans, which is what stops a scanned manual being
    indexed on the strength of the page number stamped over each image."""
    path = build(
        tmp_path,
        [
            Page(texts=(Text("11", 540.0, 760.0),), images=(Image(0.0, 0.0, 612.0, 700.0),)),
            Page(texts=(Text("12", 540.0, 760.0),), images=(Image(0.0, 0.0, 612.0, 700.0),)),
        ],
    )

    document = extract_document(path)
    assert document.has_text_layer is True  # nothing has marked furniture yet

    for page in document.pages:  # what stage 3 will do to those two lines
        for line in page.lines:
            line.furniture = True
    assert document.has_text_layer is False


def test_one_line_of_real_text_is_a_text_layer(tmp_path: Path) -> None:
    """3.3 is about having none at all; 3.4 is what covers having very little."""
    path = build(tmp_path, [Page(texts=lines("Connect the pads.", top=100)), Page()])

    assert extract_document(path).has_text_layer is True


# --- Sparse text: 3.4 -------------------------------------------------------------------


def test_a_sparse_text_layer_sets_low_text_and_is_still_extracted(tmp_path: Path) -> None:
    """3.4: ingested with the flag set, never rejected. A pictorial guide is a source."""
    path = build(
        tmp_path,
        [
            Page(
                texts=lines("Pad sensitivity", "Turn the dial clockwise.", top=100),
                images=(Image(72.0, 200.0, 400.0, 400.0, resolution=128),),
            )
        ]
        * 4,
    )

    document = extract_document(path)
    assert document.has_text_layer is True
    assert document.word_count / document.page_count < LOW_TEXT_WORDS_PER_PAGE
    assert document.low_text is True


def test_an_ordinary_manual_is_not_low_text(tmp_path: Path) -> None:
    path = build(tmp_path, [prose_page(120) for _ in range(3)])

    assert extract_document(path).low_text is False


def test_low_text_counts_the_whole_text_layer_not_just_the_english(tmp_path: Path) -> None:
    """3.4 is computed on extracted text **before** language selection.

    Counting after selection would flag every multilingual guide for having translations:
    the APC guide averages 360 words a page extracted and roughly a quarter of that once
    the Spanish, French, Italian and German pages are dropped. Here each page carries 30
    English words and 60 translated ones - low_text on the English alone, and not on the
    text layer, which is what is counted.
    """
    english = "Press the button to arm the track for recording in the session view now."
    translated = "Pulse el boton para armar la pista y grabar en la vista de sesion ahora."
    pages = [
        Page(
            texts=(
                *lines(*([english] * 2), top=100),
                *lines(*([translated] * 4), top=200),
            )
        )
        for _ in range(3)
    ]
    path = build(tmp_path, pages)

    document = extract_document(path)
    english_words = sum(
        len(span.text.split()) for span in document.spans if span.text.strip().startswith("Press")
    )
    assert english_words / document.page_count < LOW_TEXT_WORDS_PER_PAGE
    assert document.low_text is False


# --- Fidelity: 3.1, 3.2, 3.5 ------------------------------------------------------------


def test_every_span_keeps_its_page_bbox_font_size_and_flags(tmp_path: Path) -> None:
    """3.1 and 3.2, and the geometry every later stage depends on."""
    path = build(
        tmp_path,
        [
            Page(texts=(Text("Trigger", 31.5, 92.0, 7.98, HELVETICA_BOLD),)),
            Page(texts=(Text("Kick", 31.5, 92.0, 7.98, HELVETICA),)),
        ],
    )

    first, second = extract_document(path).pages
    assert (first.number, second.number) == (1, 2)
    assert (first.width, first.height) == (612.0, 792.0)

    (heading,) = first.spans
    assert heading.text == "Trigger"
    assert heading.font == HELVETICA_BOLD
    assert heading.size == pytest.approx(7.98)
    assert heading.flags != 0  # PyMuPDF's serif/bold/italic bits, kept verbatim
    x0, y0, x1, y1 = heading.bbox
    assert x0 == pytest.approx(31.5)
    assert y0 < 92.0 < y1  # the baseline sits inside the box
    assert x1 > x0

    (body,) = second.spans
    assert body.font == HELVETICA
    assert body.flags != heading.flags


def test_wording_ordering_and_casing_survive(tmp_path: Path) -> None:
    """3.1: the words reach the index as written."""
    written = ["MIDI Note Number", "Set the Kick pad to 36.", "See Chapter 5 (Advanced)."]
    path = build(tmp_path, [Page(texts=lines(*written, top=100))])

    assert [line.text.strip() for line in extract_document(path).pages[0].lines] == written


def test_a_numbered_procedure_survives_as_discrete_steps(tmp_path: Path) -> None:
    """3.5: line boundaries and the leading enumerator, so the steps stay readable."""
    steps = ("1. Connect the pads.", "2. Press Play.", "3. Turn the dial clockwise.")
    path = build(tmp_path, [Page(texts=(*lines("Setup", top=100), *lines(*steps, top=140)))])

    page = extract_document(path).pages[0]
    assert [line.text.strip() for line in page.lines][1:] == list(steps)
    tops = [line.bbox[1] for line in page.lines]
    assert tops == sorted(tops)  # line boxes are kept, so the order is recoverable


def test_a_bullet_keeps_its_marker(tmp_path: Path) -> None:
    path = build(tmp_path, [Page(texts=lines("• Arm the track.", top=100))])

    assert extract_document(path).pages[0].lines[0].text.strip().startswith("•")


def test_spans_on_one_baseline_stay_one_line(tmp_path: Path) -> None:
    """A bold lead-in and the sentence it opens are two spans of one line, which is what
    lets glyph repair key on the font without losing the line."""
    path = build(
        tmp_path,
        [
            Page(
                texts=(
                    Text("Scene Launch buttons:", 72.0, 100.0, 10.0, HELVETICA_BOLD),
                    Text(" press to launch the row.", 190.0, 100.0, 10.0, HELVETICA),
                )
            )
        ],
    )

    (line,) = extract_document(path).pages[0].lines
    assert [span.font for span in line.spans] == [HELVETICA_BOLD, HELVETICA]
    assert line.text == "Scene Launch buttons: press to launch the row."


# --- Page numbering ---------------------------------------------------------------------


def test_page_numbers_are_physical_and_one_based(tmp_path: Path) -> None:
    path = build(tmp_path, [prose_page(20) for _ in range(5)])

    document = extract_document(path)
    assert [page.number for page in document.pages] == [1, 2, 3, 4, 5]
    assert document.page_count == 5


def test_extracting_a_page_range_keeps_the_documents_own_page_count(tmp_path: Path) -> None:
    """Fixture capture takes a slice; 3.4 still divides by the whole document (task 11)."""
    path = build(tmp_path, [prose_page(200) for _ in range(6)])

    document = extract_document(path, pages=[3, 4])
    assert [page.number for page in document.pages] == [3, 4]
    assert document.page_count == 6


def _keys(value: object) -> set[str]:
    """Every key name anywhere in a nested snapshot."""
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()
