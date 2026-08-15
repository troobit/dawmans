"""English content selection — requirements 4.1-4.6, stage 6 of the run.

A multilingual guide prints the same facts five times, and indexing all five returns the
same answer five times in languages the owner cannot read. Selection is **content-side**:
`lingua`, offline, constrained to the languages the corpus actually holds plus English,
with no page range anywhere in the code or in configuration. A newly added multilingual
manual needs no change here, which is 4.2.

**A source declared with a single ISO 639-1 code is not scored at all.** There is nothing
in it to exclude, so detection can only produce false negatives, and one of them is
expensive: Live's Chapter 41 is 3,979 words over 23 pages with 24 sentence-final full stops
in the entire chapter, because it is almost all `Windows | Mac | Ctrl Shift S` tables. No
identifier calls that English. The content is English by declaration (4.1), 4.5 cannot fire
for such a source, and the 4.4 audit is still written with every page included.

Where the declared language is `multi`, scoring runs at **block** granularity — finer than
4.3's page, so a page holding two translations contributes only its English part — with two
guards, both because the identifier is unreliable on the text a manual is full of:

- **Short blocks.** Under 8 words a block is not scored. It inherits the nearest scored
  block above it on the page, else the nearest below (a page whose first block is its
  heading has nothing above), else the page's own decision.
- **Unconfident blocks.** Top confidence under 0.5 is not a verdict, so the block inherits
  the same way. The design writes this guard as low confidence *and* predominantly
  non-alphabetic tokens — the Nitro Max MIDI note table, the APC specifications table, the
  content the guard exists to keep. Measured against the real APC guide, the `and` leaks
  the other way: `• Mac OS X : Live > Preferences` on the French page scores English at
  0.42 with alphabetic tokens, is trusted, and the French step below it then inherits
  *from it* and is indexed as English. Confidence alone covers strictly more than the pair
  did — a table of numerals is unconfident too — so nothing the guard protected is lost
  (decision_log.md Decision 12).

A page with no scored block at all inherits the decision of the nearest decided page — its
predecessor, else its successor, the same order the block rule uses. A document with no
scored block anywhere is included, so a picture book is not rejected under 4.5 for being
unreadable to a language identifier.

The audit (4.4) is `english_pages` / `excluded_pages` / `partial_pages`, and the property
that governs it is that included and excluded together cover every page exactly once, with
`partial` a subset of *included*: a page is partial because part of it was kept, so it is an
included page with an exclusion inside it. The design's illustrative audit lists page 1 as
both excluded and partial, which cannot both be true of one page; the property is what is
implemented.

The APC guide prints its own language index on the front page (`English ( 3 - 6 )`). It is
deliberately not parsed — that is exactly the per-manual structure 4.2 forbids depending on
— and content-side detection reaches p23 anyway, which is what 4.6 asks for.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from dawmans.corpus.loader import Rejection
from dawmans.corpus.pdf.extract import Block, Document, Page

#: The languages in the corpus, plus English. Constraining the identifier to them is what
#: stops a Spanish page being called Portuguese with high confidence and excluded for the
#: wrong reason. This is a language set, not per-manual structure: adding a manual in a
#: sixth language adds its code here and changes nothing else.
CORPUS_LANGUAGES: tuple[str, ...] = ("en", "es", "fr", "it", "de")

ENGLISH = "en"

#: The declared-language value that turns detection on (2.3's filename grammar).
MULTILINGUAL = "multi"

#: Under this many words a block is not scored. Short-string identification is unreliable,
#: and a heading is almost always short.
SCORED_MIN_WORDS = 8

#: Below this confidence the identifier has not decided anything, and the block inherits
#: its neighbour's decision rather than carrying its own.
NEUTRAL_CONFIDENCE = 0.5

#: `(language, confidence)`, as the identifier returns it.
Detection = tuple[str, float]
Detector = Callable[[str], Detection | None]


@dataclass(frozen=True)
class Selection:
    """The 4.4 audit, plus the 4.5 rejection where there was no English at all."""

    english_pages: tuple[tuple[int, int], ...] = ()
    excluded_pages: tuple[tuple[int, int], ...] = ()
    partial_pages: tuple[int, ...] = ()
    rejection: Rejection | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "english_pages": [list(span) for span in self.english_pages],
            "excluded_pages": [list(span) for span in self.excluded_pages],
            "partial_pages": list(self.partial_pages),
        }


def select_english(document: Document, *, lang: str, detector: Detector | None = None) -> Selection:
    """Mark the English blocks of `document` in place and return the 4.4 audit.

    `lang` is the source's **declared** language, from its filename (2.3). Anything but
    `multi` means the whole document is that language by declaration and the detector is
    never called.
    """
    if lang != MULTILINGUAL:
        for page in document.pages:
            for block in page.blocks:
                block.english = True
        return _audit(document)

    detect = detector or lingua_detector()
    scored = [_score_page(page, detect) for page in document.pages]
    _inherit(document.pages, scored)
    return _audit(document)


def _score_page(page: Page, detect: Detector) -> list[bool | None]:
    """Each block's verdict, or `None` where it was not scored and has to inherit."""
    verdicts: list[bool | None] = []
    for block in page.blocks:
        verdicts.append(_score_block(block, detect))
    return verdicts


def _score_block(block: Block, detect: Detector) -> bool | None:
    if block.word_count < SCORED_MIN_WORDS:
        return None
    result = detect(block.text)
    if result is None:
        return None
    language, confidence = result
    block.lang = language
    if confidence < NEUTRAL_CONFIDENCE:
        return None
    return language == ENGLISH


def _inherit(pages: Sequence[Page], scored: list[list[bool | None]]) -> None:
    """Resolve every unscored block, then write the decisions onto the blocks."""
    page_verdicts = [_page_verdict(verdicts) for verdicts in scored]
    resolved = _resolve_pages(page_verdicts)

    for page, verdicts, fallback in zip(pages, scored, resolved, strict=True):
        for index, block in enumerate(page.blocks):
            verdict = verdicts[index]
            if verdict is None:
                verdict = _nearest(verdicts, index)
            block.english = fallback if verdict is None else verdict


def _page_verdict(verdicts: list[bool | None]) -> bool | None:
    """A page is decided when anything on it was scored; English wins on a mixed page,
    because the page contributes its English part (4.3)."""
    decided = [verdict for verdict in verdicts if verdict is not None]
    if not decided:
        return None
    return any(decided)


def _resolve_pages(verdicts: list[bool | None]) -> list[bool]:
    """Each page's fallback: itself, else the nearest decided page above, else below, else
    included — a document nothing could be scored in is not a foreign document."""
    resolved: list[bool] = []
    for index, verdict in enumerate(verdicts):
        if verdict is None:
            verdict = _nearest(verdicts, index)
        resolved.append(True if verdict is None else verdict)
    return resolved


def _nearest(verdicts: Sequence[bool | None], index: int) -> bool | None:
    """The nearest decided neighbour: above first, then below."""
    for offset in range(index - 1, -1, -1):
        if verdicts[offset] is not None:
            return verdicts[offset]
    for offset in range(index + 1, len(verdicts)):
        if verdicts[offset] is not None:
            return verdicts[offset]
    return None


def _audit(document: Document) -> Selection:
    """The 4.4 record, from the marks now on the blocks."""
    included: list[int] = []
    excluded: list[int] = []
    partial: list[int] = []
    for page in document.pages:
        english = [block for block in page.blocks if block.english]
        if english or not page.blocks:
            included.append(page.number)
            if len(english) != len(page.blocks):
                partial.append(page.number)
        else:
            excluded.append(page.number)

    rejection = None
    if not included:
        rejection = Rejection(
            reason="no-english-content",
            detail=f"no English content in {len(excluded)} pages of a `multi` source",
        )
    return Selection(
        english_pages=_ranges(included),
        excluded_pages=_ranges(excluded),
        partial_pages=tuple(partial),
        rejection=rejection,
    )


def _ranges(numbers: Sequence[int]) -> tuple[tuple[int, int], ...]:
    """`[3, 4, 5, 6, 23]` as `((3, 6), (23, 23))`."""
    spans: list[tuple[int, int]] = []
    for number in numbers:
        if spans and number == spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], number)
        else:
            spans.append((number, number))
    return tuple(spans)


@lru_cache(maxsize=1)
def _lingua(languages: tuple[str, ...]) -> Any:
    from lingua import IsoCode639_1, LanguageDetectorBuilder

    # `IsoCode639_1` is a Rust-backed class rather than a Python enum: it has the members
    # as attributes and neither subscripting nor iteration.
    codes = [getattr(IsoCode639_1, code.upper()) for code in languages]
    return LanguageDetectorBuilder.from_iso_codes_639_1(*codes).build()


def lingua_detector(languages: tuple[str, ...] = CORPUS_LANGUAGES) -> Detector:
    """The real identifier. `lingua` ships its models inside the package, so this needs no
    network and no cache (8.5), and the builder is held across sources because building it
    per block is the one way to make this stage slow."""
    detector = _lingua(tuple(languages))

    def detect(text: str) -> Detection | None:
        values = detector.compute_language_confidence_values(text)
        if not values:
            return None
        top = values[0]
        return (top.language.iso_code_639_1.name.lower(), float(top.value))

    return detect


__all__ = [
    "CORPUS_LANGUAGES",
    "ENGLISH",
    "MULTILINGUAL",
    "NEUTRAL_CONFIDENCE",
    "SCORED_MIN_WORDS",
    "Detection",
    "Detector",
    "Selection",
    "lingua_detector",
    "select_english",
]
