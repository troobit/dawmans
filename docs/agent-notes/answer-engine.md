# Answer engine (`src/dawmans/answer/`)

Implements `specs/api/answer-engine/`. Phases 1 (package scaffold + envelope records), 2 (the
corpus view), 3 (retrieval and scoping), 4 (narrowing from triage entries) and 5 (prompt, parser,
grounding, outcome procedure) are done.

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

## Narrowing (`narrow.py`)

- Three functions plus a lookup: `matched_entry` (first sidecar hit in supplied/fused order),
  `expand_entry` (sidecar lookup → first ≤4 causes → scope-filtered fix expansion under the
  12-passage cap), `build_narrowing` (7.8 suppression → `Narrowing` or None), `build_causes`
  (the 7.6 terminal `causes[]`). All entry-path; the `?narrow`/`?cause` sigils are the fallback
  path and live in prompt/parse, not here.
- `already_supplied` counts against the cap and is cited without re-admission; admission is
  cause order then section order, so a cap can leave a lower cause with empty `fix_cites` —
  which by the §4c rule also marks it unbacked for the turn. `unbacked_for_turn` is a derived
  property (`not fix_cites`), never a mutation of the entry (Decision 10: the engine reads the
  authored flag, never sets it).
- Interpretation choices worth knowing: "excess drops in cause order" is implemented as
  sequential admission (cause 1 keeps *all* its chunks before cause 2 gets any); a narrowing
  question with fewer than 2 surviving candidates is not asked (7.2 fixes the band at 2–4, the
  design only names the all-removed case); out-of-scope holding sources are read off the fix
  *pointer's* `source_id`, so they are named even though the passage is never resolved.
- 7.8's matching is deliberately not in the engine: `build_narrowing` takes a
  `state_supplies(candidate) -> bool` predicate (default None — the NullStateSource MVP).
  Deciding whether a state key/value "supplies a candidate's value" belongs to the caller once
  a live StateSource exists.
- Fix expansion applies `in_device_scope` for mask parity, but it is a no-op in practice:
  only sidecar-keyed (authored) passages declare devices, and fix pointers target vendor
  manuals — untestable until an authored passage can be a fix target.

## Prompt assembly (`prompt.py`)

- `SYSTEM_PROMPT` is one static module constant — the cache prefix; `assemble()` returns it by
  identity (tests assert `is`), so any per-turn variation must go in the user half. Order there:
  passages → roster → state → history → question; only passages-before-history-before-question is
  contractual (the Anthropic cache layout).
- The unselected-source roster is built from a fixed 4-field allowlist (`_ROSTER_FIELDS`), so a
  record arriving with `text` on it sheds it — 2.4 by construction, tested with a sentinel.
- History budget (Decision 8): `bounded_history` keeps newest-first within 800 × (1 − 10%) = 720
  tokens, counted by an injected `count_tokens` callable (the resident BGE tokeniser in prod, word
  count in tests). A single turn over the budget is dropped, not truncated.
- State enters via duck-typed `StateSnapshotLike` (SimpleNamespace in tests) — no import of the
  phase-6 `state/` package, which keeps stream 1 and stream 2 independent. Staleness direction
  (8.7) is emitted when any value is `saved-file` or older than 60 s.
- `narrowing_count >= 2` appends the terminal direction (forbids `?narrow`, directs
  `ranked-causes`) — the only mechanism 7.5 has, since the outcome is model-chosen.

## Framing parser (`parse.py`)

- `FramingParser` is a line-oriented incremental class (feed/close/result); `parse()` drives it
  total-over-bytes (decode `errors="replace"`). Property-tested with arbitrary binary.
- `CONTENT_OUTCOMES` (the seven-member line-1 enum) lives here; `outcome.py` imports it — that
  direction avoids a cycle.
- The unparsed path (invalid line 1) classifies §4d blocks but hoists **nothing**: a hoisted
  `?narrow` on a coverage-derived `answered` would put `narrowing` on an outcome that forbids it.
  Sigil lines there degrade to paragraphs (§4b rule 2).
- `framing: "unparsed"` has two producers: the fallback path, and a `!conflict` arity violation on
  an otherwise-parsed stream (the model's outcome stands in that case). Blocks are never re-typed.
- Blocks carry `markers` (all ids, in order) with marker text left inline; `Reading`s inside
  `Conflict` carry their own. `?cause` is the exception: markers are hoisted into `cites[]` and
  stripped from statement/check, because a `Cause` is a record, not streamed prose.
- `!suggest` resolution: dedupe by emitted order, drop ids absent from `sources`, cap 3 **after**
  dropping, `None` (absent) when nothing survives.

## Grounding (`ground.py`, `dawmans/triage/terms.py`)

- `dawmans/triage/terms.py` was created here (symptom-triage has landed no code) holding only the
  2.6 extraction primitives — `capitalised_runs`, `numeric_literals`. Policy (device discards,
  sentence-start rule, containment) stays with the future triage loader. `ground.terms is terms`
  is asserted so the reuse can't silently become a reimplementation. `test_no_pymupdf` picks the
  package up automatically.
- `ground_turn` scans **only** output text (direct_answer + blocks) against `supplied` — history
  and state non-citability are structural, not filtered. Unknown markers are stripped and counted;
  resolved ones stay inline. Citations dedupe in first-appearance order.
- `build_citation` is a plain-dict field copy (`page` = `page_start`, `hardware_applicability` =
  the source's `status` string). `unbacked_for_turn=True` forces the mark without touching the
  passage record — the 7.6/Decision-10 per-turn reading.
- Ungrounded arms: (a) fact-shaped over marker-stripped text — 2+-token capitalised runs, numeric
  literals, menu paths (`>`/`→`, ground's own regex; not a triage class); (b) `OrderedStep` only —
  bullets deliberately excluded. The numeric regex treats any trailing word as a unit ("2 causes"
  matches); fine for presence-testing, would need a unit lexicon for containment.

## Outcome procedure (`outcome.py`)

- Two gate chains over frozen input records (`GateState`, `Flight`) so hypothesis can attack
  totality/disjointness directly; `classify()` composes pre-flight → in-flight → line-1 enum →
  coverage fallback (`answered`/`refused-not-covered`, the single overlap).
- In-flight order is load-bearing and tested: `cancelled` first, then `streamed` (any failure
  after ≥1 token ⇒ `incomplete`, whatever the kind), then unreachable / rate-limited (unrounded
  `retry_after`, absent stays absent) / timeout (detail names the provider) / auth ⇒
  `provider-error`+`authentication-failed` / error ⇒ `provider-rejected`.
- `resolve_device` matches casefolded against gap ids and display names, both member shapes
  (bare string or `{device, ...}`, same reading as `scope.py`). `required_manual_for` keys
  presence on **resolution through the report**, not on the name containing `/` — a free-form
  `roland/tr-8s` yields no filename. Placeholders are always `(doctype, version, lang)`: a gap
  device is by definition one the engine has never seen a document for.
