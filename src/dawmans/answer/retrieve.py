"""Query embed, dense, lexical, fusion, scope mask, device filter.

Per turn, in design §Retrieval's order: embed the question with the BGE
query prefix, build the candidate mask — the selected sources' row slices
minus rows failing the device predicate — rank each retriever over the
masked rows only, and fuse with RRF at k=10 (Decision 1).

Masking precedes top-k on both retrievers. Retrieve-then-mask would let
out-of-scope and device-filtered rows consume the depth slots, so a narrow
scope against the 1009-page Live manual could return a nearly empty pool
while the index held plenty — a masking bug that would look like poor
coverage. Masking rather than slicing keeps row indices global, and one
selected source and all selected sources are the same code path: the mask
is just narrower or wider, so 5.4 and 5.8 have no special case.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import bm25s
import numpy as np

from dawmans.answer.scope import device_scope, in_device_scope
from dawmans.answer.view import CorpusView

# BGE asymmetric retrieval: the question carries the query instruction;
# passages were embedded bare with their citation header.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@dataclass(frozen=True)
class RetrievalConfig:
    """Retrieval constants.

    Both threshold arms are guesses until the evaluation set exists
    (design §The relevance threshold) and calibrating them is that set's
    first job — configuration, never literals in the paths that apply them.
    """

    dense_tau: float = 0.30  # τ dense arm: cosine ≥ this qualifies
    rare_term_df: float = 0.05  # τ lexical arm: shared-term df as a share of the corpus
    depth: int = 50  # per-retriever pool
    rrf_k: int = 10  # Decision 1, not the published 60
    base_cap: int = 8  # Decision 5
    narrowing_cap: int = 12  # 1.3, reached only on a narrowing expansion


DEFAULT_CONFIG = RetrievalConfig()


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> Iterable[np.ndarray]: ...


def embed_query(embedder: Embedder, question: str) -> np.ndarray:
    """The question under the BGE query prefix, unit-normalised so that
    `vectors @ q` over the L2-normalised passage vectors is cosine."""
    [vector] = list(embedder.embed([QUERY_PREFIX + question]))
    vector = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def tokenize_query(question: str) -> tuple[str, ...]:
    """The index build's tokenisation applied to the question — same
    pattern, no stopword list — so query terms land in the index vocabulary."""
    [tokens] = bm25s.tokenize(
        question, stopwords=None, return_ids=False, show_progress=False
    )
    return tuple(tokens)


def rrf_scores(
    rankings: Sequence[Sequence[str]], k: int = DEFAULT_CONFIG.rrf_k
) -> dict[str, float]:
    """score(c) = Σ_retrievers 1/(k + rank(c)), ranks 1-based."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, candidate in enumerate(ranking, start=1):
            scores[candidate] = scores.get(candidate, 0.0) + 1.0 / (k + rank)
    return scores


def fuse(rankings: Sequence[Sequence[str]], k: int = DEFAULT_CONFIG.rrf_k) -> list[str]:
    """RRF order; ties broken by passage_id, so the fused order is a pure
    function of the ranks and invariant to arrival order."""
    scores = rrf_scores(rankings, k)
    return sorted(scores, key=lambda candidate: (-scores[candidate], candidate))


def candidate_mask(
    view: CorpusView, selected_source_ids: Iterable[str], scope: frozenset[str]
) -> np.ndarray:
    """Rows in the selected sources' slices, minus rows failing the device
    predicate — the only place where "filter, not rank" holds by
    construction rather than by discipline (5.13)."""
    mask = np.zeros(len(view.passages), dtype=bool)
    for source_id in selected_source_ids:
        mask[view.row_slice(source_id)] = True
    for row in np.flatnonzero(mask):
        if not in_device_scope(view, view.passages[row]["passage_id"], scope):
            mask[row] = False
    return mask


@dataclass(frozen=True, eq=False)
class CandidatePool:
    """Steps 1–5 of a turn's retrieval: everything before the threshold."""

    scope: frozenset[str]
    mask: np.ndarray  # boolean, one entry per view row
    cosines: np.ndarray  # vectors @ q; meaningful under the mask
    bm25: np.ndarray  # lexical scores, zeroed by the weight mask
    tokens: tuple[str, ...]  # the tokenised question
    dense: tuple[str, ...]  # depth-k dense ranking over masked rows
    lexical: tuple[str, ...]  # depth-k lexical ranking over masked rows
    fused: tuple[str, ...]  # RRF order, ties by passage_id
    fused_scores: Mapping[str, float]


def _ranked(scores: np.ndarray, rows: np.ndarray, pids: np.ndarray, depth: int) -> np.ndarray:
    # Score descending, ties by passage_id, cut to depth. A bare
    # argpartition would leave boundary ties in arrival order; at ~1,200
    # rows the full lexsort costs microseconds and keeps the ranking a pure
    # function of the scores, which the fusion invariance property needs.
    if rows.size == 0:
        return rows
    order = np.lexsort((pids[rows], -scores[rows]))
    return rows[order][:depth]


def _lexical_scores(lexical, tokens: Sequence[str], mask: np.ndarray) -> np.ndarray:
    # The mask is a weight mask: scores are zeroed before any top-k, so a
    # masked row cannot hold a slot.
    known = [token for token in tokens if token in lexical.vocab_dict]
    if not known:
        return np.zeros(int(lexical.scores["num_docs"]), dtype=np.float32)
    return np.asarray(
        lexical.get_scores(known, weight_mask=mask.astype(np.float32)),
        dtype=np.float32,
    )


def candidate_pool(
    view: CorpusView,
    question: str,
    query: np.ndarray,
    selected_source_ids: Iterable[str],
    *,
    config: RetrievalConfig = DEFAULT_CONFIG,
) -> CandidatePool:
    """Build the fused candidate pool for a turn.

    Operates wholly on the loaded view — no network, no filesystem beyond
    the mmapped vectors the view already holds.
    """
    selected = tuple(selected_source_ids)
    scope = device_scope(view, selected)
    mask = candidate_mask(view, selected, scope)
    rows = np.flatnonzero(mask)
    tokens = tokenize_query(question)

    if rows.size == 0:
        empty = np.zeros(len(view.passages), dtype=np.float32)
        return CandidatePool(scope, mask, empty, empty, tokens, (), (), (), {})

    pids = np.array([record["passage_id"] for record in view.passages])
    cosines = np.asarray(view.vectors @ np.asarray(query, dtype=np.float32), dtype=np.float32)
    dense_rows = _ranked(cosines, rows, pids, config.depth)

    bm25 = _lexical_scores(view.lexical, tokens, mask)
    lexical_rows = _ranked(bm25, rows[bm25[rows] > 0.0], pids, config.depth)

    dense_ids = tuple(str(pid) for pid in pids[dense_rows])
    lexical_ids = tuple(str(pid) for pid in pids[lexical_rows])
    fused_scores = rrf_scores([dense_ids, lexical_ids], config.rrf_k)
    fused = tuple(
        sorted(fused_scores, key=lambda candidate: (-fused_scores[candidate], candidate))
    )
    return CandidatePool(
        scope, mask, cosines, bm25, tokens, dense_ids, lexical_ids, fused, fused_scores
    )


@dataclass(frozen=True)
class ScoredPassage:
    """One passage supplied to synthesis, with the signals that put it there."""

    passage_id: str
    source_id: str
    cosine: float
    bm25: float
    fused: float
    qualifying: bool


@dataclass(frozen=True, eq=False)
class Retrieval:
    """Step 6 applied to the pool: threshold, per-source floor, cap.

    Empty `supplied` with a non-empty selected set means no in-scope
    candidate qualified: the turn is uncovered per 2.1, never synthesised
    from weak matches. `qualifying_sources` is in the turn's selected-source
    order.
    """

    pool: CandidatePool
    supplied: tuple[ScoredPassage, ...]
    qualifying_sources: tuple[str, ...]


def _rare_term_rows(lexical, tokens: Sequence[str], df_share: float) -> set[int]:
    # bm25s stores per-token document postings CSC-style: indptr[t]..
    # indptr[t+1] slices the doc indices holding token t, so a term's
    # document frequency is the slice length — no re-tokenisation of the
    # corpus and no second index.
    indptr = lexical.scores["indptr"]
    indices = lexical.scores["indices"]
    limit = df_share * int(lexical.scores["num_docs"])
    rows: set[int] = set()
    for token in dict.fromkeys(tokens):
        token_id = lexical.vocab_dict.get(token)
        if token_id is None:
            continue
        start, stop = int(indptr[token_id]), int(indptr[token_id + 1])
        if 0 < stop - start <= limit:
            rows.update(int(row) for row in indices[start:stop])
    return rows


def _qualifying(
    view: CorpusView, pool: CandidatePool, selected: Sequence[str], config: RetrievalConfig
) -> tuple[set[int], list[str]]:
    """τ per source: a candidate qualifies on cosine ≥ the dense threshold,
    or on BM25 rank 1 *within its own source* while sharing a rare query
    term. Per-source, not global: a global rank 1 qualifies at most one
    candidate corpus-wide, so the 5-page APC guide holding the decisive
    rare term would qualify for nothing and 5.6's floor would never fire."""
    rare = _rare_term_rows(view.lexical, pool.tokens, config.rare_term_df)
    pids = [record["passage_id"] for record in view.passages]
    rows_qualifying: set[int] = set()
    sources: list[str] = []
    for source_id in selected:
        source_rows = np.arange(len(pids))[view.row_slice(source_id)]
        source_rows = source_rows[pool.mask[source_rows]]
        if source_rows.size == 0:
            continue
        qualifying = set(source_rows[pool.cosines[source_rows] >= config.dense_tau])
        scored = source_rows[pool.bm25[source_rows] > 0.0]
        if scored.size:
            top = min(scored, key=lambda row: (-pool.bm25[row], pids[row]))
            if int(top) in rare:
                qualifying.add(top)
        if qualifying:
            rows_qualifying.update(int(row) for row in qualifying)
            sources.append(source_id)
    return rows_qualifying, sources


def retrieve(
    view: CorpusView,
    question: str,
    query: np.ndarray,
    selected_source_ids: Iterable[str],
    *,
    narrowing_expansion: bool = False,
    config: RetrievalConfig = DEFAULT_CONFIG,
) -> Retrieval:
    """A turn's retrieval: pool, threshold, floor, cap — design §Retrieval."""
    selected = tuple(selected_source_ids)
    pool = candidate_pool(view, question, query, selected, config=config)
    qualifying_rows, qualifying_sources = _qualifying(view, pool, selected, config)
    if not qualifying_rows:
        return Retrieval(pool, (), ())

    # Effective cap (Decision 5): never above 12 (1.3) except that 5.6's
    # floor takes precedence — beyond 12 qualifying sources the cap rises to
    # one passage per qualifying source and admits nothing further.
    cap = max(
        config.base_cap,
        len(qualifying_sources),
        config.narrowing_cap if narrowing_expansion else 0,
    )

    source_of = {pid: view.passages_by_id[pid]["source_id"] for pid in pool.fused}
    pending = set(qualifying_sources)
    chosen: set[str] = set()
    for pid in pool.fused:  # the floor: one slot per qualifying source, in fused order
        if source_of[pid] in pending:
            pending.discard(source_of[pid])
            chosen.add(pid)
    # A qualifying source can miss both depth cuts entirely; its floor slot
    # is then its best qualifying candidate by the dense signal.
    row_pids = {row: view.passages[row]["passage_id"] for row in qualifying_rows}
    extras = [
        min(
            (row for row in qualifying_rows if view.passages[row]["source_id"] == source_id),
            key=lambda row: (-pool.cosines[row], row_pids[row]),
        )
        for source_id in qualifying_sources
        if source_id in pending
    ]
    extra_ids = [row_pids[row] for row in extras]

    for pid in pool.fused:  # remaining slots by fused rank
        if len(chosen) + len(extra_ids) >= cap:
            break
        chosen.add(pid)

    rows = np.flatnonzero(pool.mask)
    row_of = {view.passages[row]["passage_id"]: int(row) for row in rows}
    supplied = tuple(
        ScoredPassage(
            passage_id=pid,
            source_id=view.passages_by_id[pid]["source_id"],
            cosine=float(pool.cosines[row_of[pid]]),
            bm25=float(pool.bm25[row_of[pid]]),
            fused=float(pool.fused_scores.get(pid, 0.0)),
            qualifying=row_of[pid] in qualifying_rows,
        )
        for pid in [pid for pid in pool.fused if pid in chosen] + extra_ids
    )
    return Retrieval(pool, supplied, tuple(qualifying_sources))
