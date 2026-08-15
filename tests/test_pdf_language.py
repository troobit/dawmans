"""English content selection — requirements 4.1-4.6, stage 6.

The rule that decides everything here is that a source declared with a single ISO 639-1
code is **not scored at all**. Live's Chapter 41 is the case that settles it: 3,979 words
over 23 pages with 24 sentence-final full stops in the whole chapter, because it is almost
entirely `Windows | Mac | Ctrl Shift S | Cmd Shift S` tables. No language identifier calls
that English, and scoring it would delete the most exact-match-heavy content in the corpus
— visible only in the 4.4 audit, months later.

Detection therefore runs only where the declared language is `multi`, at block granularity,
with two guards that both exist because the identifier is unreliable on short and on
symbolic text.

The redacted `apc_pages` fixture cannot exercise a language identifier — its text is masked
to character classes, so no word of the copyrighted guide is committed — and it is not
meant to. Its hand-written labels are ground truth, and what these tests drive is the
*selection* machinery: the guards, the inheritance and the audit. `lingua` itself is
exercised once, on prose written here.
"""

from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st

from conftest import FIXTURE_DIR
from dawmans.corpus.pdf.extract import Block, Document
from dawmans.corpus.pdf.language import (
    CORPUS_LANGUAGES,
    MULTILINGUAL,
    SCORED_MIN_WORDS,
    Detection,
    lingua_detector,
    select_english,
)
from spanmodel import document_of, page_of, text_block

ENGLISH = "Press the button to arm the track for recording before you start the transport."
SPANISH = "Pulse el botón para armar la pista de grabación antes de iniciar el transporte."
FRENCH = "Appuyez sur le bouton pour armer la piste avant de lancer le transport du logiciel."
NUMERALS = "36 38 40 48 50 45 47 43 58"
#: The measured false positive: English words printed on a French page, scored English with
#: no confidence at all. `lingua` returns 0.42 for it.
UI_PATH = "• Mac OS X : Live > Preferences > MIDI Sync tab"

SCORED: dict[str, Detection] = {
    ENGLISH: ("en", 0.93),
    SPANISH: ("es", 0.98),
    FRENCH: ("fr", 0.97),
    UI_PATH: ("en", 0.42),
}


def fixture(name: str) -> Document:
    raw = (FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")
    return Document.from_dict(json.loads(raw))


def stub(text: str) -> Detection | None:
    """A stand-in for the identifier: confident on the prose written above, and as lost on
    a table of numerals as `lingua` measurably is (it returns 0.0 for one)."""
    return SCORED.get(text.strip(), ("it", 0.05))


def tripwire(text: str) -> Detection | None:
    raise AssertionError(f"scored a source declared with one language: {text[:40]!r}")


def label_detector(document: Document):
    """The fixture's hand-written labels, resolved by the text they were written against.

    Where one masked text carries two labels across the guide — `0 0 0 0 …`, the same
    table of numerals set on six translations of one page — no identifier could do better
    than a coin flip, so the stub returns the low confidence a real one would and the
    language-neutral guard decides what happens next.
    """
    by_text: dict[str, set[str]] = {}
    for page in document.pages:
        for block in page.blocks:
            if block.lang:
                by_text.setdefault(block.text, set()).add(block.lang)

    def detect(text: str) -> Detection | None:
        labels = by_text.get(text)
        if not labels:
            return None
        if len(labels) > 1:
            return (sorted(labels)[0], 0.05)
        return (next(iter(labels)), 0.99)

    return detect


def prose_pages(*pages: tuple[str, ...], first: int = 1) -> Document:
    """One page per argument, one block per string on it."""
    return document_of(
        *(
            page_of(
                number,
                *(text_block(body, top=100.0 + i * 40.0) for i, body in enumerate(bodies)),
            )
            for number, bodies in enumerate(pages, start=first)
        )
    )


# --- A declared language is not scored (4.1) ------------------------------------------------


def shortcut_chapter() -> Document:
    """A stand-in for Live pp984-1006: keyboard-shortcut tables, almost no sentences.

    The real chapter is not a committed fixture — 23 pages of it would be 23 pages of a
    copyrighted guide — so the shape is reproduced here: short rows, two full stops in the
    whole chapter, and nothing a language identifier can call English.
    """
    rows = ("Windows | Mac", "Ctrl Shift S | Cmd Shift S", "Ctrl Alt L | Cmd Alt L", "F9 | F9")
    pages = [
        page_of(
            number,
            *(text_block(row, top=100.0 + index * 30.0) for index, row in enumerate(rows)),
        )
        for number in range(984, 1007)
    ]
    return Document(page_count=1009, pages=pages)


def test_a_source_declared_with_one_language_is_never_scored() -> None:
    """4.1 by declaration. The detector is a tripwire: it must not be reached at all."""
    document = shortcut_chapter()
    selection = select_english(document, lang="en", detector=tripwire)

    assert selection.to_dict() == {
        "english_pages": [[984, 1006]],
        "excluded_pages": [],
        "partial_pages": [],
    }
    assert all(block.english for page in document.pages for block in page.blocks)
    assert selection.rejection is None


def test_a_declared_source_cannot_be_rejected_for_having_no_english() -> None:
    """4.5 cannot fire for a source that was never scored — there is nothing to exclude."""
    document = prose_pages((SPANISH,), (SPANISH,))
    selection = select_english(document, lang="es", detector=tripwire)

    assert selection.rejection is None
    assert selection.to_dict()["english_pages"] == [[1, 2]]


# --- The APC guide (4.2, 4.6) ------------------------------------------------------------------


def test_the_translations_are_excluded_and_the_appendix_is_kept() -> None:
    """pp3-6 are the English guide and p23 the English appendix, which is 4.6: English
    content outside the main English section, reached by content and not by a page range."""
    document = fixture("apc_pages")
    selection = select_english(document, lang=MULTILINGUAL, detector=label_detector(document))
    included = set(_flatten(selection.english_pages))
    excluded = set(_flatten(selection.excluded_pages))

    assert {3, 4, 5, 6, 23} <= included
    assert set(range(7, 23)) == excluded
    assert included | excluded == {page.number for page in document.pages}
    assert not included & excluded


def test_the_selection_does_not_depend_on_where_the_pages_are() -> None:
    """4.2: no page range in the code or in configuration. Renumbering every page moves the
    same decision with it — nothing keys off a page number."""
    document = fixture("apc_pages")
    shifted = fixture("apc_pages")
    for page in shifted.pages:
        page.number += 100

    first = select_english(document, lang=MULTILINGUAL, detector=label_detector(document))
    second = select_english(shifted, lang=MULTILINGUAL, detector=label_detector(shifted))

    assert [n - 100 for n in _flatten(second.english_pages)] == list(_flatten(first.english_pages))


def test_the_printed_language_index_is_not_parsed() -> None:
    """The APC front page prints `English ( 3 - 6 )`, `Appendix English ( 23 )`. It is
    exactly the per-manual structure 4.2 forbids depending on, so removing it entirely
    changes nothing about which pages are selected."""
    document = fixture("apc_pages")
    without = fixture("apc_pages")
    without.pages[0].blocks = []

    full = select_english(document, lang=MULTILINGUAL, detector=label_detector(document))
    stripped = select_english(without, lang=MULTILINGUAL, detector=label_detector(without))

    assert _flatten(stripped.english_pages) == _flatten(full.english_pages)


# --- The two guards (4.3) ------------------------------------------------------------------------


def test_a_short_block_inherits_the_scored_block_above_it() -> None:
    """Short-string identification is unreliable, and a heading dropped from an English
    page is a citation with a hole in it."""
    document = prose_pages((ENGLISH, "Arming a track"), (SPANISH, "Armar una pista"))
    select_english(document, lang=MULTILINGUAL, detector=stub)

    assert [block.english for block in document.pages[0].blocks] == [True, True]
    assert [block.english for block in document.pages[1].blocks] == [False, False]
    assert len("Arming a track".split()) < SCORED_MIN_WORDS


def test_a_heading_at_the_top_of_a_page_inherits_from_below() -> None:
    """The common case: a page whose first block is its heading has nothing above it."""
    document = prose_pages(("Arming a track", ENGLISH), ("Armar una pista", SPANISH))
    select_english(document, lang=MULTILINGUAL, detector=stub)

    assert [block.english for block in document.pages[0].blocks] == [True, True]
    assert [block.english for block in document.pages[1].blocks] == [False, False]


def test_a_page_with_nothing_scored_inherits_its_predecessor() -> None:
    document = prose_pages((SPANISH,), ("Panel trasero",), (SPANISH,))
    selection = select_english(document, lang=MULTILINGUAL, detector=stub)

    assert list(_flatten(selection.excluded_pages)) == [1, 2, 3]


def test_the_first_page_of_a_document_with_nothing_scored_is_included() -> None:
    """Nothing scored anywhere is not evidence of a foreign document, and 4.5 must not
    fire on a picture book."""
    document = prose_pages(("Front panel",), ("Rear panel",))
    selection = select_english(document, lang=MULTILINGUAL, detector=stub)

    assert list(_flatten(selection.english_pages)) == [1, 2]
    assert selection.rejection is None


def test_a_table_of_numbers_is_not_discarded_as_non_english() -> None:
    """The Nitro Max MIDI note table and the APC specifications table: top confidence under
    0.5 and predominantly non-alphabetic tokens. Without this guard the pages that answer
    'which note does the kick send' are the ones that go."""
    document = prose_pages(
        (ENGLISH, NUMERALS, "20 Hz - 20 kHz, 0.5 dB"),
    )
    select_english(document, lang=MULTILINGUAL, detector=stub)

    assert all(block.english for block in document.pages[0].blocks)


def test_an_unconfident_block_of_words_inherits_rather_than_being_trusted() -> None:
    """Measured on the real APC guide: `• Mac OS X : Live > Preferences` on the French page
    scores English at 0.42 with alphabetic tokens. Trusting it puts a French page in the
    index — the step below it is short and inherits *from it* (decision_log Decision 12).
    """
    document = prose_pages((FRENCH, UI_PATH, "4. Cliquez sur l'onglet MIDI/Sync."))
    selection = select_english(document, lang=MULTILINGUAL, detector=stub)

    assert [block.english for block in document.pages[0].blocks] == [False, False, False]
    assert selection.rejection is not None


def test_a_confident_block_is_taken_at_its_word() -> None:
    """The guard is a bound on unconfident verdicts and nothing more: a confident Spanish
    paragraph on an English page is still excluded."""
    document = prose_pages((ENGLISH, SPANISH))
    select_english(document, lang=MULTILINGUAL, detector=stub)

    assert [block.english for block in document.pages[0].blocks] == [True, False]


# --- The audit (4.4) --------------------------------------------------------------------


def test_a_page_selected_in_part_is_included_and_listed_as_partial() -> None:
    """4.3 selects at finer than page granularity, and 4.4 says a sub-page selection is
    visible rather than hidden inside a whole-page range."""
    document = prose_pages((ENGLISH, FRENCH), (ENGLISH,))
    selection = select_english(document, lang=MULTILINGUAL, detector=stub)

    assert selection.to_dict() == {
        "english_pages": [[1, 2]],
        "excluded_pages": [],
        "partial_pages": [1],
    }
    assert [block.english for block in document.pages[0].blocks] == [True, False]


def test_the_audit_reports_contiguous_ranges() -> None:
    document = prose_pages((ENGLISH,), (ENGLISH,), (SPANISH,), (SPANISH,), (FRENCH,), (ENGLISH,))
    selection = select_english(document, lang=MULTILINGUAL, detector=stub)

    assert selection.to_dict()["english_pages"] == [[1, 2], [6, 6]]
    assert selection.to_dict()["excluded_pages"] == [[3, 5]]


BODIES = st.sampled_from([ENGLISH, SPANISH, FRENCH, NUMERALS, "Arming a track", ""])


@given(pages=st.lists(st.lists(BODIES, min_size=1, max_size=4), min_size=1, max_size=6))
def test_the_audit_covers_every_page_exactly_once(pages: list[list[str]]) -> None:
    """Audit completeness (design §Property-based tests). The audit is the only record of
    what was dropped, so a page missing from both lists is content that vanished with
    nothing saying so."""
    document = prose_pages(*(tuple(bodies) for bodies in pages))
    selection = select_english(document, lang=MULTILINGUAL, detector=stub)

    included = list(_flatten(selection.english_pages))
    excluded = list(_flatten(selection.excluded_pages))
    numbers = [page.number for page in document.pages]

    assert sorted(included + excluded) == numbers
    assert not set(included) & set(excluded)
    assert set(selection.partial_pages) <= set(included)


# --- Rejection (4.5) --------------------------------------------------------------------


def test_a_source_with_no_english_content_is_rejected() -> None:
    document = prose_pages((SPANISH,), (FRENCH,), (SPANISH, "Panel trasero"))
    selection = select_english(document, lang=MULTILINGUAL, detector=stub)

    assert selection.rejection is not None
    assert selection.rejection.reason == "no-english-content"
    assert selection.english_pages == ()
    assert list(_flatten(selection.excluded_pages)) == [1, 2, 3]


# --- The identifier itself --------------------------------------------------------------


def test_the_default_detector_is_lingua_over_the_corpus_languages() -> None:
    """`lingua` ships its models in the package, so this runs offline (8.5). The language
    set is the corpus's plus English, which is what stops a Spanish page being called
    Portuguese with high confidence and excluded for the wrong reason."""
    detect = lingua_detector()

    assert detect(ENGLISH)[0] == "en"
    assert detect(SPANISH)[0] == "es"
    assert detect(FRENCH)[0] == "fr"
    assert set(CORPUS_LANGUAGES) == {"en", "es", "fr", "it", "de"}


def test_the_identifier_is_not_confident_about_a_table_of_numerals() -> None:
    """Which is why the language-neutral guard exists rather than trusting the top hit."""
    language, confidence = lingua_detector()(NUMERALS)

    assert confidence < 0.5
    assert language in CORPUS_LANGUAGES


def test_selection_runs_with_the_real_identifier_end_to_end() -> None:
    """No stub anywhere: a multilingual document, scored by `lingua`."""
    document = prose_pages((ENGLISH,), (SPANISH,), (FRENCH,), (ENGLISH,))
    selection = select_english(document, lang=MULTILINGUAL)

    assert list(_flatten(selection.english_pages)) == [1, 4]
    assert list(_flatten(selection.excluded_pages)) == [2, 3]


def _flatten(ranges: tuple[tuple[int, int], ...]) -> list[int]:
    return [number for first, last in ranges for number in range(first, last + 1)]


def _blocks(document: Document) -> list[Block]:
    return [block for page in document.pages for block in page.blocks]


def test_a_block_carries_the_language_it_was_scored_as() -> None:
    """`Block.lang` is what the detector returned, and it is what the report reads."""
    document = prose_pages(
        (ENGLISH, SPANISH),
    )
    select_english(document, lang=MULTILINGUAL, detector=stub)

    assert [block.lang for block in _blocks(document)] == ["en", "es"]


def test_a_line_is_never_removed_by_selection() -> None:
    """Stage 6 marks blocks; the drop is the chunker's, and 4.4's audit is the record."""
    document = prose_pages((ENGLISH,), (SPANISH,))
    before = [line.text for page in document.pages for line in page.lines]

    select_english(document, lang=MULTILINGUAL, detector=stub)

    assert [line.text for page in document.pages for line in page.lines] == before
