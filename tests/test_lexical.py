"""The lexical index and its tokeniser — requirement 8.8 and decision_log Decision 2.

8.8 requires **exact-term matching** over the indexed passages: a passage containing a
query term literally, "including model names, version strings, hyphenated and slashed
tokens and bare numerals". This corpus is dense with exactly those — `Dry/Wet`, `4th-gen`,
`bge-small-en-v1.5`, MIDI note `38` — because they are what a user reads off a screen and
types verbatim.

**The failure this file exists to catch is silent.** A default tokeniser splits `Dry/Wet`
into two ordinary words and drops the compound; nothing errors, the index builds, and the
query a user is most confident about is the one that stops working. So the first tests
below assert the default behaviour is what Decision 2 says it is, and then that ours is
not it — a tokeniser test that only checked our own output would pass just as happily
against a tokeniser that had quietly regressed to the default.

Ordering is the other contract. Document `i` of this index is line `i` of
`passages.jsonl` and row `i` of `vectors.npy`, which is what lets `api/answer-engine`
fuse the two rankings and scope either to a source by slice.
"""

from __future__ import annotations

from pathlib import Path

import bm25s
import pytest

from dawmans.index.lexical import LexicalIndex, tokenise

# One passage per line, in the order they would be written to `passages.jsonl`.
PASSAGES = [
    "The Dry/Wet control sets how much of the processed signal is heard.",
    "Trigger 38 is the snare and trigger 39 is the closed hi-hat.",
    "The Scarlett Solo 4th-gen interface has two inputs on the front panel.",
    "Passages are embedded with bge-small-en-v1.5 at 384 dimensions.",
    "Turn the knob to make the sound quieter as the phrase ends.",
]

TERMS = ["Dry/Wet", "4th-gen", "bge-small-en-v1.5", "38", "74"]


# --- The failure Decision 2 names ---------------------------------------------------------


@pytest.mark.parametrize("term", ["Dry/Wet", "4th-gen", "bge-small-en-v1.5"])
def test_the_default_tokeniser_loses_the_compound_terms(term: str) -> None:
    """Not a test of `bm25s` — a test of the premise. If a future version kept these, the
    custom tokeniser below would be carrying a cost for nothing and this would say so."""
    (tokens,) = bm25s.tokenize([term], return_ids=False, show_progress=False)

    assert term.lower() not in tokens


# --- The tokeniser (8.8) ------------------------------------------------------------------


@pytest.mark.parametrize("term", TERMS)
def test_every_named_term_survives_as_a_retrievable_token(term: str) -> None:
    """The whole compound is kept, so a user typing what is printed on the screen matches
    it exactly. Bare numerals are in the list because they are the worst case for the dense
    index: 38 and 39 embed almost identically while the right answer differs completely."""
    assert term.lower() in tokenise(term)


def test_a_compound_also_yields_its_parts() -> None:
    """Kept *as well as* the compound, not instead of it: a user who types `wet` should
    still reach the Dry/Wet control, and one who types `Dry/Wet` should reach it exactly."""
    tokens = tokenise("Dry/Wet")

    assert tokens[0] == "dry/wet"
    assert set(tokens) == {"dry/wet", "dry", "wet"}


def test_tokens_are_casefolded_and_stripped_of_surrounding_punctuation() -> None:
    """A term at the end of a sentence, in parentheses or in quotes is the same term."""
    assert tokenise('The "Dry/Wet" knob (see 4th-gen).') == [
        "the",
        "dry/wet",
        "dry",
        "wet",
        "knob",
        "see",
        "4th-gen",
        "4th",
        "gen",
    ]


def test_a_separator_run_collapses_rather_than_producing_an_odd_term() -> None:
    """A double hyphen is how some manuals set a dash. Left alone it would make the
    compound depend on the vendor's punctuation, and a user typing `mid-side` would miss
    it; an empty part would be a term matching everything."""
    assert tokenise("mid--side") == ["mid-side", "mid", "side"]
    assert "" not in tokenise("...38...")


def test_text_with_no_alphanumeric_content_yields_no_tokens() -> None:
    assert tokenise("— ‖ ·") == []


def test_section_numbers_survive_whole_and_in_parts() -> None:
    """`(1.3.1)` is a printed section number and `§24.9` a citation the user may copy."""
    assert tokenise("(1.3.1)") == ["1.3.1", "1", "3", "1"]
    assert tokenise("§24.9") == ["24.9", "24", "9"]


# --- The index (8.8, 8.10) ----------------------------------------------------------------


def test_an_exact_compound_query_finds_the_passage_that_prints_it() -> None:
    index = LexicalIndex.build(PASSAGES)

    assert index.search("Dry/Wet")[0][0] == 0
    assert index.search("4th-gen")[0][0] == 2
    assert index.search("bge-small-en-v1.5")[0][0] == 3


def test_a_bare_numeral_distinguishes_two_passages_a_dense_index_could_not() -> None:
    """`38` and `39` are the Nitro Max trigger table's primary use case, and the case
    Decision 2 names as the worst for embeddings alone."""
    index = LexicalIndex.build([*PASSAGES, "Trigger 74 is the ride cymbal."])

    assert index.search("74")[0][0] == 5
    assert index.search("38")[0][0] == 1


def test_document_numbers_are_the_passage_line_numbers_they_were_built_from() -> None:
    """The correspondence the view rests on: document `i` here is line `i` of
    `passages.jsonl` and row `i` of `vectors.npy`."""
    index = LexicalIndex.build(PASSAGES)

    assert index.document_count == len(PASSAGES)
    assert {rank for rank, _ in index.search("trigger")} == {1}


def test_a_query_term_no_passage_holds_matches_nothing() -> None:
    """Zero-scoring documents are dropped rather than returned as a filled-out top-k, so a
    caller cannot mistake padding for a match."""
    assert LexicalIndex.build(PASSAGES).search("compressor") == []


def test_a_lexical_index_alone_does_not_satisfy_the_criterion() -> None:
    """8.8's own words: neither kind of matching alone satisfies it. The last passage is
    about fading a sound out, and a question asking for exactly that in different words
    shares no term with it, so BM25 cannot reach it at any rank. That is why the dense
    index is built over the same passages rather than instead of them."""
    index = LexicalIndex.build(PASSAGES)

    assert index.search("gradually reduce loudness towards its finish") == []


# --- The saved artefact -------------------------------------------------------------------


def test_the_index_saves_to_the_views_lexical_directory_and_loads_back(tmp_path: Path) -> None:
    """`lexical/` is a directory, which is why the whole view is committed by renaming
    `manifest.json` last: no single file rename can swap it."""
    directory = tmp_path / "views" / "7f1c2a" / "lexical"
    LexicalIndex.build(PASSAGES).save(directory)

    loaded = LexicalIndex.load(directory)

    assert directory.is_dir()
    assert loaded.document_count == len(PASSAGES)
    assert loaded.search("Dry/Wet")[0][0] == 0


def test_an_empty_corpus_still_produces_a_loadable_index(tmp_path: Path) -> None:
    """A run in which every source was rejected still commits a view, and a reader must be
    able to load it and get no matches rather than an unreadable directory."""
    directory = tmp_path / "lexical"
    LexicalIndex.build([]).save(directory)

    loaded = LexicalIndex.load(directory)

    assert loaded.document_count == 0
    assert loaded.search("Dry/Wet") == []


def test_search_never_returns_more_hits_than_there_are_documents(tmp_path: Path) -> None:
    """`k` defaults above the corpus size on a small view, and the underlying library pads
    its top-k rather than shortening it."""
    index = LexicalIndex.build(PASSAGES[:2])

    assert len(index.search("the", limit=50)) <= 2
