"""The bm25s wrapper — requirement 8.8, decision_log Decision 2.

8.8 requires exact-term matching over the indexed passages, "including model names,
version strings, hyphenated and slashed tokens and bare numerals", alongside the
meaning-based matching `vectors.npy` provides. Neither alone satisfies it, so both are
built over the same passage ordering: document `i` here is line `i` of `passages.jsonl`
and row `i` of `vectors.npy`.

**The tokeniser is the whole of the risk.** A default one splits `Dry/Wet` into two
ordinary words and drops the compound, `4th-gen` into `4th` and `gen`, and
`bge-small-en-v1.5` into four fragments. Nothing errors — the index builds and the query
a user is most confident about is the one that silently stops working. So a token is kept
**whole and in parts**: the compound so that what is printed on the screen matches
exactly, the parts so that a user who types one word of it still arrives.

Ranking is not this spec's business. `api/answer-engine` owns fusion and relevance
(Decision 2); what is built here is the artefact that leaves the choice open.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import bm25s

#: The characters that may appear *inside* a token without ending it. Everything else
#: separates. `-` and `/` are Decision 2's own cases; `.` carries version strings and
#: printed section numbers; `_` carries identifiers copied out of a file name.
SEPARATORS = "-/._"

#: One token: alphanumeric runs joined by separators. Anchored, so a match is the whole of
#: what is left after the surrounding punctuation is stripped.
_TOKEN = re.compile(rf"[a-z0-9]+(?:[{re.escape(SEPARATORS)}]+[a-z0-9]+)*")
_SEPARATOR_RUN = re.compile(rf"[{re.escape(SEPARATORS)}]+")

#: The document a corpus of none is indexed as. `bm25s` cannot index an empty vocabulary,
#: and a run in which every source was rejected still commits a view that a reader must be
#: able to load. No tokeniser output can equal it — every real token starts alphanumeric —
#: so it can never be matched, and `document_count` keeps it out of every result.
_PLACEHOLDER = "\x00empty"


def tokenise(text: str) -> list[str]:
    """The terms a passage is retrievable by, in the order they are printed.

    Casefolded, punctuation-stripped, and each compound kept **whole followed by its
    parts**. `Dry/Wet` yields `dry/wet`, `dry`, `wet`; `bge-small-en-v1.5` yields the whole
    identifier and its five fragments. A query goes through this same function, so a user
    typing the compound matches the compound and one typing a fragment matches the
    fragment.

    An intermediate compound is not emitted — `v1.5` inside `bge-small-en-v1.5` is not a
    term of its own. Adding every subsequence would multiply the vocabulary for a case no
    query in this corpus has needed; the whole identifier and its parts cover Decision 2's
    named failures.

    **No stopword list is applied**, and that is deliberate rather than an omission.
    `bm25s`'s English list holds `on` but not `off`, so applying it would make one half of
    every `On`/`Off` control in this corpus unretrievable while leaving the other half
    matchable — a worse outcome than either extreme. A common word carries almost no IDF
    weight anyway, and ranking is `api/answer-engine`'s to decide (Decision 2).
    """
    tokens: list[str] = []
    for match in _TOKEN.finditer(text.casefold()):
        # A run of separators collapses to its first, so `mid--side` is the term a user
        # typing `mid-side` reaches. Splitting drops the run either way; the compound is
        # the half that would otherwise depend on how the manual set its punctuation.
        whole = _SEPARATOR_RUN.sub(lambda run: run.group()[0], match.group())
        tokens.append(whole)
        parts = [part for part in _SEPARATOR_RUN.split(whole) if part]
        if len(parts) > 1:
            tokens.extend(parts)
    return tokens


class LexicalIndex:
    """A BM25 index over one view's passages, in that view's own order."""

    def __init__(self, retriever: bm25s.BM25, document_count: int) -> None:
        self.retriever = retriever
        #: How many of the indexed documents are real passages. It differs from what the
        #: retriever holds only for an empty corpus, which is indexed as one placeholder.
        self.document_count = document_count

    @classmethod
    def build(cls, texts: Sequence[str]) -> LexicalIndex:
        """Index each text as one document, keeping the caller's order.

        The text passed in is the chunk's citation-header-prefixed encoding, the same
        string the dense index embeds (Decision 2), so a query naming the manual or the
        section reaches the passage through either index.
        """
        corpus = [tokenise(text) for text in texts] or [[_PLACEHOLDER]]
        retriever = bm25s.BM25()
        retriever.index(corpus, show_progress=False)
        return cls(retriever, document_count=len(texts))

    def save(self, directory: Path) -> None:
        """Write the view's `lexical/` directory.

        It is a **directory**, which cannot be swapped by a single file rename — which is
        why the whole view is built fresh and `manifest.json` renamed into place last.
        """
        directory.parent.mkdir(parents=True, exist_ok=True)
        self.retriever.save(str(directory), show_progress=False)
        (directory / "document_count").write_text(f"{self.document_count}\n")

    @classmethod
    def load(cls, directory: Path) -> LexicalIndex:
        retriever = bm25s.BM25.load(str(directory), show_progress=False)
        count = int((directory / "document_count").read_text())
        return cls(retriever, document_count=count)

    def search(self, query: str, limit: int = 10) -> list[tuple[int, float]]:
        """`(document number, score)` for the matching passages, best first.

        Zero-scoring documents are dropped rather than returned as a filled-out top-k: the
        library pads its result to `k`, and a caller cannot tell padding from a match.
        Ranking beyond that ordering belongs to `api/answer-engine` (Decision 2).
        """
        if not self.document_count:
            return []
        tokens = tokenise(query)
        if not tokens:
            return []

        documents, scores = self.retriever.retrieve(
            [tokens], k=min(limit, self.document_count), show_progress=False
        )
        return [
            (int(document), float(score))
            for document, score in zip(documents[0], scores[0], strict=True)
            if score > 0.0 and document < self.document_count
        ]


__all__ = ["SEPARATORS", "LexicalIndex", "tokenise"]
