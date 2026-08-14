"""Furniture marking — requirement 3.6, stage 3.

Stage 3 **marks**; it deletes nothing. The mark is cleared again by stage 5 on any line a
section anchor resolves to and by stage 7 inside a detected table, and only what is still
marked at the end of stage 7 is dropped. Every test here asserts against that ordering:
the assertion is on `Line.furniture`, never on missing text.

The property is the one that matters. Suppression is invisible in the output — text that
was never indexed produces no diff and no error — so the safety net is a bound on what may
be suppressed at all: a line whose normalised key occurs on exactly one page is not
repeated boilerplate, whatever it looks like, and is never marked.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from conftest import FIXTURE_DIR
from dawmans.corpus.pdf.extract import Document
from dawmans.corpus.pdf.furniture import (
    BAND,
    REPEAT_RATIO,
    key_of,
    mark_furniture,
)
from spanmodel import HEIGHT, block_of, document_of, footer, header, page_of, text_line

RUNNING_TITLE = "Ableton Live 12 Reference Manual"


def fixture(name: str) -> Document:
    raw = (FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")
    return Document.from_dict(json.loads(raw))


def marked(document: Document) -> list[str]:
    return [line.text.strip() for page in document.pages for line in page.lines if line.furniture]


def numbered_pages(count: int, *, first: int = 1) -> Document:
    """`count` pages, each printing its own number in the bottom band and a line of body."""
    return document_of(
        *(
            page_of(
                number,
                block_of(text_line(f"Set the input gain on channel {number}.", top=200.0)),
                footer(str(number)),
            )
            for number in range(first, first + count)
        )
    )


# --- The property: what may be suppressed at all -----------------------------------------


@given(
    pages=st.lists(
        st.lists(st.sampled_from(["12", "Getting Started", "Appendix A", "3.4", ""]), max_size=3),
        min_size=1,
        max_size=8,
    )
)
def test_a_line_whose_key_occurs_on_one_page_is_never_suppressed(pages: list[list[str]]) -> None:
    """Furniture safety (design §Property-based tests). The rule that decides is the
    normalised key, so `23` on p23 and `24` on p24 are one key on two pages, while a
    heading printed once is a key on one page and out of reach of every rule here."""
    document = document_of(
        *(
            page_of(
                number,
                *(footer(text, x0=72.0 + index * 40.0) for index, text in enumerate(texts)),
                block_of(text_line("Body text well clear of either band.", top=200.0)),
            )
            for number, texts in enumerate(pages, start=1)
        )
    )
    mark_furniture(document)

    seen: dict[str, set[int]] = {}
    for page in document.pages:
        for line in page.lines:
            if line.text.strip():
                seen.setdefault(key_of(line.text), set()).add(page.number)

    for page in document.pages:
        for line in page.lines:
            if line.furniture:
                assert len(seen[key_of(line.text)]) > 1, line.text


def test_a_heading_printed_once_survives_even_inside_the_band() -> None:
    document = numbered_pages(6)
    document.pages[2].blocks.append(header("Chapter 3: Recording"))
    mark_furniture(document)

    assert "Chapter 3: Recording" not in marked(document)


# --- Stage 3 marks, and marks only --------------------------------------------------------


def test_marking_deletes_nothing() -> None:
    """Clearing is stages 5 and 7 and the drop is at the end of stage 7, so the span model
    coming out of stage 3 differs from the one going in by the marks alone."""
    document = numbered_pages(5)
    before = document.to_dict()

    assert mark_furniture(document) == 5

    after = document.to_dict()
    assert _without_marks(after) == before
    assert [page.text for page in document.pages] == [
        f"Set the input gain on channel {number}.\n{number}" for number in range(1, 6)
    ]


def _without_marks(snapshot: dict) -> dict:
    """The snapshot writes `furniture` only where it is set, so dropping the key is the
    whole difference stage 3 is allowed to make."""
    return {
        **snapshot,
        "pages": [
            {
                **page,
                "blocks": [
                    {
                        **block,
                        "lines": [
                            {key: value for key, value in line.items() if key != "furniture"}
                            for line in block["lines"]
                        ],
                    }
                    for block in page["blocks"]
                ],
            }
            for page in snapshot["pages"]
        ],
    }


# --- What is marked -----------------------------------------------------------------------


def test_a_repeated_page_number_in_the_band_is_marked() -> None:
    document = numbered_pages(10)
    mark_furniture(document)

    assert marked(document) == [str(number) for number in range(1, 11)]


def test_a_page_number_that_alternates_left_and_right_is_still_one_key() -> None:
    """Recto and verso print the number at opposite margins; the y-band is what has to be
    consistent, not the x. The Nitro Max prints it at x=355 on odd pages and x=33 on even."""
    document = document_of(
        *(
            page_of(
                number,
                block_of(text_line("Body.", top=200.0)),
                footer(str(number), x0=320.0 if number % 2 else 72.0),
            )
            for number in range(1, 9)
        )
    )
    mark_furniture(document)

    assert len(marked(document)) == 8


def test_a_running_title_is_marked_when_it_repeats_across_the_document() -> None:
    """The repeated-key rule exists for the manual that prints one; no guide in this
    corpus does, which is why the digits-only rule does the work here."""
    document = numbered_pages(10)
    for page in document.pages:
        page.blocks.insert(0, header(RUNNING_TITLE))
    mark_furniture(document)

    assert marked(document).count(RUNNING_TITLE) == 10


def test_a_running_title_at_an_inconsistent_height_is_not_marked() -> None:
    """`at a consistent y-band` (design §Furniture removal): the same words drifting down
    the page are a heading that happens to recur, not a running header."""
    document = numbered_pages(10)
    for offset, page in enumerate(document.pages):
        page.blocks.insert(
            0, block_of(text_line(RUNNING_TITLE, top=2.0 + offset * 4.0, width=80.0))
        )
    mark_furniture(document)

    assert RUNNING_TITLE not in marked(document)


def test_a_repeated_line_outside_the_bands_is_not_marked() -> None:
    """Only the top and bottom 8% are candidates. A warning printed in the body of every
    page is repeated text and not page furniture, and 3.6 names headers, footers and page
    numbers."""
    document = numbered_pages(10)
    for page in document.pages:
        page.blocks.append(block_of(text_line("Do not connect phantom power.", top=HEIGHT * 0.5)))
    mark_furniture(document)

    assert "Do not connect phantom power." not in marked(document)


def test_a_digits_only_line_is_marked_below_the_repeat_threshold() -> None:
    """The digits-only rule is the lenient one: a guide that prints the number on the
    chapter pages only never reaches 60%, and those numbers are still furniture."""
    document = numbered_pages(10)
    for page in document.pages[2:]:
        page.blocks = [page.blocks[0]]  # the number is printed on pp1-2 alone
    mark_furniture(document)

    assert marked(document) == ["1", "2"]
    assert 2 / 10 < REPEAT_RATIO


def test_a_digits_only_line_on_one_page_alone_is_not_marked() -> None:
    """Even the lenient rule stops at the safety property."""
    document = numbered_pages(10)
    for page in document.pages[1:]:
        page.blocks = [page.blocks[0]]
    mark_furniture(document)

    assert marked(document) == []


def test_a_short_document_marks_at_five_pages() -> None:
    """`>=5 pages in a document of <=10`: 5 of 10 is under the 60% threshold and is still
    a running header, because 60% of a ten-page guide is six pages."""
    document = numbered_pages(10)
    for page in document.pages[:5]:
        page.blocks.insert(0, header(RUNNING_TITLE))
    mark_furniture(document)

    assert marked(document).count(RUNNING_TITLE) == 5
    assert 5 / 10 < REPEAT_RATIO


# --- The key --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("23", "#"),
        ("Page 23", "page #"),
        ("PAGE  23", "page #"),
        ("  Page\t23 ", "page #"),
        ("Chapter 3.4", "chapter #.#"),
        ("23 | Ableton Live", "# | ableton live"),
    ],
)
def test_the_key_collapses_case_whitespace_and_digit_runs(text: str, expected: str) -> None:
    """Digit runs collapse because a page number is different text on every page and the
    same furniture on all of them."""
    assert key_of(text) == expected


# --- Against the corpus ----------------------------------------------------------------------


def test_furniture_pages_marks_the_page_number_and_nothing_in_the_table() -> None:
    """3.6 against Nitro Max pp23-26. p25 is the MIDI note table: its numeric cells are
    printed in the body of the page, so the band restriction alone keeps them — stage 7's
    clear inside a detected table is the backstop for a table that reaches into the band,
    not the thing that saves this page."""
    document = fixture("furniture_pages")
    mark_furniture(document)

    assert marked(document) == ["23", "24", "25", "26"]

    table = next(page for page in document.pages if page.number == 25)
    numeric = [line for line in table.lines if line.text.strip().isdigit()]
    assert len(numeric) > 19  # the trigger-to-note pairs, plus the page number
    assert [line.text.strip() for line in numeric if line.furniture] == ["25"]


def test_furniture_pages_leaves_the_body_of_every_page_intact() -> None:
    document = fixture("furniture_pages")
    mark_furniture(document)

    for page in document.pages:
        band = page.height * BAND
        for line in page.lines:
            if line.furniture:
                assert line.bbox[3] <= band or line.bbox[1] >= page.height - band
