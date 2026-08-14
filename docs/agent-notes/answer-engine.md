# Answer engine (`src/dawmans/answer/`)

Implements `specs/api/answer-engine/`. Phases 1 (package scaffold + envelope records), 2 (the
corpus view) and 3 (retrieval and scoping) are done.

## Package setup

- First Python code in the repo: `src/` layout, hatchling, uv. `pyproject.toml` was created here
  even though the manual-corpus design nominally establishes the package — that spec had landed no
  code when this branch started, so the scaffold includes `src/dawmans/__init__.py` and `cli.py`
  (with only the `serve` stub registered; `ingest`/`validate`/`inventory` land with manual-corpus).
- Dependency split is load-bearing, not tidiness: `[project.optional-dependencies] ingest` holds
  PyMuPDF (AGPL) + lingua + fonttools; `serve` holds fastembed, bm25s, numpy, anthropic, starlette,
  uvicorn, keyring. The API host runs `uv sync --extra serve` and must never install `ingest`.
  `lingua-py` is `lingua-language-detector` on PyPI.
- `tests/answer/test_no_pymupdf.py` imports every `dawmans.answer.*` module in a subprocess with a
  `sys.meta_path` finder poisoning `fitz` and `pymupdf`. It walks packages dynamically and picks up
  `dawmans.triage` automatically once that package exists — no test change needed then.
- `make test` / `make lint` (ruff + spelling) / `make build` are configured; use them.

## Envelope records (`envelope.py`)

- `Citation`, `AnswerEnvelope`, `Cause`, `RequiredManual` are frozen dataclasses whose field sets
  are exactly the CONTRACTS §3/§4/§4c/§4e tables; tests assert set equality on
  `dataclasses.fields`, so adding a field means amending CONTRACTS first.
- Frozen but NOT slotted — `frozen=True, slots=True` breaks the unknown-attribute error path (see
  `rules/language-rules/python.md` in agentic-coding).
- Invariants enforced in `__post_init__` rather than by tests alone: absent-is-None (empty strings
  rejected), authored-triage citations reject `doc_version`/`section_number`/`page`,
  `entry_location` is authored-only, `causes[n].rank == n+1`, `retry_after >= 0` and unrounded,
  `framing` ∈ {parsed, unparsed}.
- `Outcome` (17) and `Reason` (5) are StrEnums mirroring CONTRACTS §6/§6a; the envelope validates
  membership at construction so an unlisted member cannot exist.
- Helper shapes not named as CONTRACTS records but implied by its payloads: `SourceRef`
  (`suggested_sources[]`/`scope_dropped[]` members), `Narrowing`/`NarrowingCandidate`,
  `RequiredDevice`, `Timings` (durations only; `corpus_reload_ms` is run-level).
- `body` is an untyped tuple for now; §4d block types arrive with `parse.py`.

## Corpus view (`view.py`)

- Two classes: `CorpusView` is one immutable revision of the merged view (frozen dataclass,
  `eq=False` because it holds a memmap and a bm25s object); `ViewWatcher` owns the mutable
  `view` reference, the stat cache, `manifest_fault` and `corpus_reload_ms`. A turn holds the
  `CorpusView` object it started with — the swap only replaces `watcher.view`, which is what makes
  "an in-flight turn keeps its files" true with no extra machinery.
- `dawmans.records` / `dawmans.index.*` don't exist yet (manual-corpus has landed no code), so the
  view holds `sources`/`passages` as plain dicts parsed from JSON. When those modules land, typing
  can be introduced here without changing the load order.
- Sidecar loading keys off `kind == "authored-triage"` in `sources.json`, derives the filename with
  `sidecar_name()` (slug rule: `/`→`_`), and raises `ViewLoadError` when the file is absent — the
  hyphenated-spelling silent failure from `data/symptom-triage` §The sidecar.
- `ViewWatcher.check()` semantics worth knowing:
  - stat key is `(st_mtime_ns, st_size)`; tests force distinct stats with an explicit `os.utime`
    bump rather than trusting filesystem timestamp granularity.
  - an unreadable/wrong-version *new* manifest keeps the live view and sets `manifest_fault`
    (consumed by GET /sources in phase 8); the stat cache is still advanced so the bad manifest is
    not re-parsed every turn. Same policy for a manifest that parses but whose view fails to load.
  - a *missing* manifest is not a fault: `view` becomes `None`, which the outcome gate maps to
    `corpus-empty`.
  - startup with a present-but-unreadable manifest raises (refuse to serve); startup with no
    manifest starts with `view = None`.
- `from_manifest` cross-checks `sum(row_count) == len(passages) == vectors.shape[0]` and fails
  loudly on mismatch — cheap guard for the no-mixed-revisions invariant.

## Retrieval and scoping (`scope.py`, `retrieve.py`)

- `scope.py` holds `device_scope` (5.12) and `in_device_scope` (5.13). Scope derivation branches
  on *whether any vendor-manual is selected*, not on which: none selected → every indexed
  vendor-manual device plus the gaps. Gap members are accepted as either bare device-id strings or
  `{device, ...}` mappings — the corpus spec never pins the member shape, only that `rig.yaml`'s
  `display_name` appears in the reports.
- `retrieve.py` splits at the design's step-5/step-6 seam: `candidate_pool()` is embed → mask →
  dense → lexical → RRF (tested by `test_retrieve.py`), `retrieve()` adds τ + floor/cap allocation
  on top (tested by `test_threshold.py`). Both take the *already embedded* query vector;
  `embed_query()` is separate so tests control cosines exactly and the BGE query prefix is
  asserted in isolation.
- Ranking uses a full `np.lexsort((pids, -scores))` instead of the design table's bare
  `argpartition`: boundary ties under argpartition are arrival-ordered, which would break the
  fusion input-invariance property. Cost is µs at ~1,200 rows.
- The lexical arm's document frequencies come from bm25s internals: `lexical.scores` is a CSC-like
  dict where `indptr[t]..indptr[t+1]` slices the doc postings for token id `t` (ids via
  `vocab_dict`). df = slice length; the same slice gives "which docs share the term". No corpus
  re-tokenisation. Pinned bm25s 0.3.10 — re-check on upgrade.
- Query tokenisation is `bm25s.tokenize(question, stopwords=None, return_ids=False)`. The
  `stopwords=None` must match what the (not yet implemented) manual-corpus index build uses;
  parity is asserted only through the in-memory fixtures for now.
- `bm25.get_scores(tokens, weight_mask=mask)` returns full-corpus scores with masked rows zeroed;
  lexical candidacy additionally requires score > 0, so masked and no-overlap rows never rank.
- Fixture trick (`tests/answer/corpus_fixtures.py`): `make_view()` builds a `CorpusView` entirely
  in memory (no disk round-trip), and default vectors are `np.eye(N)` — one-hot rows make
  `vectors @ q` read the query's component per row, so tests state every cosine directly.
- Allocation subtleties: floor picks keep their fused positions (a boundary-qualifying small
  source lands *last* in `supplied`); a qualifying source that misses both depth-50 cuts still
  gets its floor slot (appended after the fused-ordered picks); cap arithmetic is
  `max(8, |qualifying|, 12 if narrowing)` in one place.
