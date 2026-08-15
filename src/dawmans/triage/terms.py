"""The term check — design 'The term check (2.6)'.

Separating a **causal** assertion the author is entitled to make (2.5) from a
**factual** one only the manual is entitled to make. The checked span is the
cause statement plus its `check:` value: `why:`, loose prose and the closing
statement are excluded, a deliberate narrowing of 2.6 that keeps 2.5's causal
assertions out of a factual check.

Two classes are extracted — capitalised runs and numeric literals — and a term is
satisfied when **any** one of the cause's pointers resolves to a passage set
containing it. Containment is case-sensitive for the capitalised class and
casefolded for the numeric one; a split section is seen as its concatenation.

A miss is a flag naming the term and the section and **never** sets `unbacked`
(Decision 5): the pointer resolved, and what failed is a heuristic over an
author's prose whose false-positive rate cannot be bounded. 2.4 and 8.5 stay the
only two producers of that mark. The gap that leaves is closed at the desk
instead — `dawmans validate` exits non-zero on a miss, where the author is
present to read it.

The design sketches this module as `terms(cause) -> list[str]`. It takes the
`Entry` as well, because two of the rules it states are properties of the whole
entry rather than of one cause: a sentence-start token is kept when it is
capitalised *elsewhere in the entry*, and a term is discarded when it names one
of the entry's *declared* devices.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from dawmans.triage.model import Cause, DeviceRef, Entry, Flag
from dawmans.triage.parse import render

MIN_TERM_LENGTH = 3
"""Tokens under three characters are dropped: `EQ`, `dB` and a bare `2` carry no
claim a manual could be expected to print."""

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*")

_NUMERIC = re.compile(
    r"""(?<![\w.])          # not the tail of a longer number or an identifier
        [-+]?\d+(?:[.,]\d+)?    # 0, -12, 44.1
        (?:\s*(?:%|[A-Za-z]{1,4}\b))?   # an optional unit: dB, kHz, ms, %
    """,
    re.VERBOSE,
)

_GAP = re.compile(r"[ \t]+")
_WHITESPACE = re.compile(r"\s+")

_SENTENCE_END = ".!?:;"
_OPENERS = "\"'“”‘’([{*_>#-•—"

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'"})
"""Manuals typeset a curly apostrophe and authors type a straight one. Folding
them together is not a relaxation of the case rule — `Saturator's` and
`Saturator’s` are the same word, spelled by two keyboards."""


# --- Extraction -------------------------------------------------------------


def terms(entry: Entry, cause: Cause, *, display_names: Collection[str] = ()) -> list[str]:
    """The factual terms of one cause, in the order the author wrote them.

    `display_names` are the `rig.yaml` display names of the entry's **declared**
    devices — the device the owner holds, not the `SourceRecord`'s document name.
    The caller holds the rig; this module only states what it reads of it.
    """
    span = f"{cause.statement}\n{cause.check}"
    corroborated = _corroborated(entry)
    vocabulary = device_vocabulary(entry.devices, display_names)

    found = sorted(_runs(span, corroborated) + _numerics(span))
    seen: dict[str, None] = {}
    for _, text in found:
        if len(text) < MIN_TERM_LENGTH or text.casefold() in vocabulary:
            continue
        seen.setdefault(text)
    return list(seen)


def device_vocabulary(
    devices: Sequence[DeviceRef], display_names: Collection[str] = ()
) -> frozenset[str]:
    """Casefolded identities that are not terms: a declared device's id, its
    product token and its display name.

    Naming the device an entry is scoped to is not a factual claim about a
    control; it is the scope, restated in prose.
    """
    vocabulary = set()
    for device in devices:
        vocabulary.add(device.id.casefold())
        _, _, product = device.id.partition("/")
        if product:
            vocabulary.add(product.casefold())
    vocabulary.update(name.casefold() for name in display_names if name)
    return frozenset(vocabulary)


def _runs(span: str, corroborated: frozenset[str]) -> list[tuple[int, str]]:
    """Consecutive capitalised or ALL-CAPS tokens, taken from the span verbatim."""
    run: list[tuple[int, int]] = []
    out: list[tuple[int, str]] = []

    def close() -> None:
        if run:
            out.append((run[0][0], span[run[0][0] : run[-1][1]]))
            run.clear()

    for text, start, end, initial in _tokens(span):
        if not _is_run_material(text, initial, corroborated):
            close()
            continue
        if run and not _GAP.fullmatch(span[run[-1][1] : start]):
            close()
        run.append((start, end))
    close()
    return out


def _numerics(span: str) -> list[tuple[int, str]]:
    """Numeric literals with an optional unit: `0 dB`, `-12 dB`, `44.1 kHz`.

    The class is where false positives concentrate and it is kept anyway: 7.3's
    mandated cause turns on a device's output running above `0 dB`, and a numeric
    claim no passage prints is exactly the claim 2.6 exists to catch.
    """
    return [
        (match.start(), _WHITESPACE.sub(" ", match.group().strip()))
        for match in _NUMERIC.finditer(span)
    ]


def _is_run_material(text: str, initial: bool, corroborated: frozenset[str]) -> bool:
    """Whether a token's capitalisation is evidence that it names something.

    A sentence start explains an initial capital on its own, so it is discounted
    unless the same word appears capitalised elsewhere in the entry. The design
    states this for a single-token run; applying it to the token rather than to
    the run is what yields the design's own example, `Track Activator`, from an
    author's "The Track Activator is off". ALL-CAPS is exempt: nothing about a
    sentence start explains `DIRECT`.
    """
    if not text[0].isupper():
        return False
    if _is_all_caps(text):
        return True
    return not initial or text.casefold() in corroborated


def _is_all_caps(text: str) -> bool:
    letters = [character for character in text if character.isalpha()]
    return len(letters) >= 2 and all(character.isupper() for character in letters)


def _corroborated(entry: Entry) -> frozenset[str]:
    """Casefolded tokens the entry capitalises somewhere other than a sentence start.

    Read over the canonical rendering, which is the entry as the user sees it:
    symptom, phrasings, preamble, every cause and the closing statement. The
    pointers are not in it, and a source id is not evidence about English prose.
    """
    return frozenset(
        text.casefold()
        for text, _, _, initial in _tokens(render(entry))
        if not initial and text[0].isupper()
    )


def _tokens(text: str) -> list[tuple[str, int, int, bool]]:
    return [
        (match.group(), match.start(), match.end(), _at_sentence_start(text, match.start()))
        for match in _TOKEN.finditer(text)
    ]


def _at_sentence_start(text: str, start: int) -> bool:
    index = start - 1
    while index >= 0 and (text[index].isspace() or text[index] in _OPENERS):
        if text[index] == "\n":
            return True
        index -= 1
    return index < 0 or text[index] in _SENTENCE_END


# --- Containment ------------------------------------------------------------


@dataclass(frozen=True)
class Resolution:
    """One pointer's resolution set, as the term check sees it.

    `label` is the pointer in the form the author wrote it, for the 5.3 message.
    `texts` are the section's passages in section order; the check reads their
    **concatenation**, because which chunk holds the sentence about a control is
    an artefact of the 350-word cap and changes under a re-chunk.
    """

    label: str
    texts: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n".join(self.texts)


@dataclass(frozen=True)
class TermMiss:
    """One term of a cause that no cited section prints."""

    term: str
    sections: tuple[str, ...]
    """Every pointer that was checked — the term is in none of them."""


def check_terms(
    entry: Entry,
    cause: Cause,
    resolutions: Sequence[Resolution],
    *,
    display_names: Collection[str] = (),
) -> list[TermMiss]:
    """The terms of one cause that no pointer's resolution set contains.

    A cause with no resolutions is not checked at all. That is 2.3's carve-out and
    a drifted pointer: there is nothing to check against, and both already carry
    `unbacked`, which says more than a list of unfound terms would.
    """
    if not resolutions:
        return []
    labels = tuple(resolution.label for resolution in resolutions)
    return [
        TermMiss(term=term, sections=labels)
        for term in terms(entry, cause, display_names=display_names)
        if not any(contains(term, resolution.text) for resolution in resolutions)
    ]


def contains(term: str, text: str) -> bool:
    """Whether a passage prints a term, at word boundaries.

    Case-sensitive for the capitalised class: terms are extracted *because* they
    are capitalised, so casefolding would make `Off`, `Monitor`, `MIDI` and `Live`
    match almost any prose and the check close to vacuous. The manuals print
    control names capitalised too, so the case-sensitive test is the one that
    discriminates. Numerals are casefolded, because unit case varies between
    manuals (`kHz`, `khz`) and carries no meaning.
    """
    haystack = text.translate(_APOSTROPHES)
    needle = term.translate(_APOSTROPHES)
    if _is_numeric(needle):
        return re.search(_pattern(needle, r"\s*"), haystack, re.IGNORECASE) is not None
    return re.search(_pattern(needle, r"\s+"), haystack) is not None


def _is_numeric(term: str) -> bool:
    """Which class a term came from. The two extractors are disjoint on this
    test: a capitalised run always opens with a letter."""
    return term[:1].isdigit() or term[:1] in "-+"


def _pattern(term: str, gap: str) -> str:
    """The term at word boundaries, tolerating how the passage wraps.

    `\\b` will not do at either end: a term may open with `-12` or close with `%`,
    neither of which is a word character, and `\\b` would then demand one beside
    it. The lookarounds ask the question that is actually meant — that the term is
    not part of a longer word or number — which is what keeps `0` from satisfying
    `10`. The gap is `\\s+` rather than a literal space so that a control name
    broken across two lines of the manual still counts.
    """
    parts = [re.escape(part) for part in term.split()]
    return r"(?<![0-9A-Za-z])" + gap.join(parts) + r"(?![0-9A-Za-z])"


def term_flag(entry: Entry, cause: Cause, miss: TermMiss) -> Flag:
    """The 5.3 message: what is wrong, and what to change in the entry's own words."""
    if len(miss.sections) == 1:
        where = f"{miss.sections[0]} does not contain that term"
    else:
        where = f"none of {', '.join(miss.sections)} contains that term"
    return Flag(
        name="term-not-in-passage",
        source_file=entry.source_file,
        symptom=entry.symptom,
        cause=cause.statement,
        detail=f'says "{miss.term}" but {where}. Point at the section that documents it.',
    )


__all__ = [
    "MIN_TERM_LENGTH",
    "Resolution",
    "TermMiss",
    "check_terms",
    "contains",
    "device_vocabulary",
    "term_flag",
    "terms",
]
