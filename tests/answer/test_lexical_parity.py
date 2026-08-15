"""The query side and the index side must tokenise identically.

`data/manual-corpus` 8.8 requires exact matching on "model names, version
strings, hyphenated and slashed tokens and bare numerals", and the custom
tokeniser in `index/lexical.py` is what delivers it — a compound is indexed
whole *and* in parts. A query tokenised by anything else reaches the parts
and never the compound: the term is in the vocabulary and unreachable, which
fails silently, since the fragments still match and an answer still comes
back with less to rank on.

That is exactly what happened. `tokenize_query` called
`bm25s.tokenize(..., stopwords=None)`, whose default splitter emits parts
only and drops single characters, so every compound in the corpus was dead
and `no sound from track 3` never matched on `3`. Nothing failed, because
the parity assertions live in fixtures that tokenise both sides with the
same function and so cannot see the two sides drift.

These tests compare the two callables directly for that reason. They are the
guard on the seam, not on either implementation.
"""

from __future__ import annotations

import pytest

from dawmans.answer.retrieve import tokenize_query
from dawmans.index.lexical import tokenise

#: 8.8's named cases, each as it would appear inside a question.
COMPOUNDS = [
    ("Dry/Wet", "dry/wet"),
    ("4th-gen", "4th-gen"),
    ("mid-side", "mid-side"),
    ("re-enable", "re-enable"),
    ("bge-small-en-v1.5", "bge-small-en-v1.5"),
    ("TS-999", "ts-999"),
]


@pytest.mark.parametrize(
    "text",
    [
        "What does the Dry/Wet control do?",
        "How do I use a mid-side EQ?",
        "no sound from track 3",
        "Is the Scarlett Solo 4th-gen supported?",
        "bge-small-en-v1.5",
        "",
    ],
)
def test_query_tokenisation_is_the_index_tokenisation(text: str) -> None:
    """The one property: same text, same terms. Not merely the same
    settings — a second implementation is how the two drifted before."""
    assert tokenize_query(text) == tuple(tokenise(text))


@pytest.mark.parametrize(("printed", "expected"), COMPOUNDS)
def test_a_compound_is_reachable_from_a_question(printed: str, expected: str) -> None:
    """The whole compound is a query term, not just its fragments — the
    half `bm25s.tokenize` dropped, and the half 8.8 is about."""
    tokens = tokenize_query(f"what does {printed} do?")
    assert expected in tokens


@pytest.mark.parametrize(("printed", "whole"), COMPOUNDS)
def test_a_compounds_parts_stay_reachable_too(printed: str, whole: str) -> None:
    """Whole *and* parts: a user who types one word of a compound still
    arrives, so the fix must not trade one arm for the other."""
    tokens = tokenize_query(f"what does {printed} do?")
    parts = [term for term in tokenise(printed) if term != whole]
    assert parts, f"{printed!r} is not a compound — the case proves nothing"
    assert all(part in tokens for part in parts)


def test_a_bare_numeral_survives() -> None:
    """`bm25s.tokenize`'s splitter needs two word characters, so a lone
    digit vanished — and "track 3" is the shape a user actually types."""
    assert "3" in tokenize_query("no sound from track 3")


def test_no_stopword_list_is_applied() -> None:
    """Decision 2: bm25s's English list holds `on` but not `off`, so
    applying it would make one half of every On/Off control unretrievable
    while leaving the other matchable. Both must survive on both sides."""
    tokens = tokenize_query("should the switch be on or off?")
    assert "on" in tokens
    assert "off" in tokens
