# Answer engine (`src/dawmans/answer/`)

Implements `specs/api/answer-engine/`. All 9 phases are done: 1 (package scaffold + envelope
records), 2 (the corpus view), 3 (retrieval and scoping), 4 (narrowing from triage entries),
5 (prompt, parser, grounding, outcome procedure), 6 (providers, credentials, state seam),
7 (conversation state, turn pipeline), 8 (the local HTTP surface) and 9 (end-to-end, serve
wiring and timing).

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

## Providers and the state seam (`provider/`, `state/`)

- **Phase-7 resolution of the SynthesisRequest tension (Decision 11):** the request gained one
  optional field, `user: str | None` — the varying prompt half pre-rendered by `prompt.assemble`.
  `user_text(req)` returns it verbatim when set and falls back to its own rendering otherwise, so
  phase-6 provider tests stand. The pipeline is the only caller of `assemble`; a request built
  without `user` silently loses the roster and the 7.5 terminal direction.
- `provider/base.py` holds the whole seam: `ProviderKind`, `requires_key(kind)` (derived, 6.4),
  `mask(key)` (the "…"+last-4 form — defined here, not in credentials, because `ProviderStatus`
  lives here), `SynthesisRequest`, `ProviderStatus`, `ProbeResult`, the four-kind
  `ProviderFailure` (`timeout` is deliberately absent — that's the engine's own watchdog), the
  `Provider` protocol, and `user_text(req)` — the **single** renderer of the varying prompt half
  shared by every provider, so 6.2 stays structural (Decision 4).
- **Known tension for phase 7:** `SynthesisRequest` is the design's verbatim shape (system,
  passages, question, history, state, max_words) but carries no roster and no narrowing counter,
  while `prompt.assemble()` handles both. The turn pipeline has to reconcile the two — either by
  widening `SynthesisRequest` (spec edit) or by folding roster/terminal-direction text into the
  fields it has. Nothing in phase 6 tests passage-block formatting, so `user_text` can change
  shape freely then.
- Anthropic provider: settings are pinned by tests (`thinking: disabled` + `effort: low`,
  `max_retries=0`, `httpx.Timeout(30.0, connect=2.0)`, cache_control on the last system block,
  model `claude-opus-5`). Token estimate for the cache-minimum check is **word count** — chars/4
  lands at ~1048 and falsely clears Sonnet 5's 1024 minimum; the design's "~600-token" figure
  tracks words (679). Rate-limit policy retries once only when a stated retry-after ≤ 3.0 s
  **and nothing has been yielded yet** (a retry after partial output would re-yield from the
  start; 6.10 owns that case as `incomplete`). `retry_after` is passed through unrounded and
  absent stays absent. `detail` is always engine wording (`"rate limited (429)"` etc.), never
  SDK exception text — that's what keeps raw payloads out of CONTRACTS §4 `detail`.
- Local provider: raw `httpx.AsyncClient` against an OpenAI-compatible `/v1/chat/completions`
  SSE stream (no `openai` dependency; `httpx` added to the serve extra explicitly). The
  constructor **raises** on a non-loopback base URL (`LOOPBACK_HOSTS`), which is how 6.14 holds
  by construction; tests additionally poison networking with a `MockTransport` that asserts
  every request host is loopback. Structural 6.12: the Anthropic constructor takes a key but no
  URL, the local one a URL but no key — asserted via `inspect.signature`.
- Shared backend: a stub. `acknowledge()` flips the 6.15 gate; `status()` reports
  `requires_disclosure_ack` until then; unacknowledged `stream()` raises as defence in depth
  (the real refusal is `outcome.pre_flight` via `GateState.requires_ack/acknowledged`). Takes an
  optional `script` so the 6.2 same-envelope test can drive all three classes with one stream.
- `credentials.py`: keyring under service `dawmans`, account `anthropic` for KEYED_HOSTED
  (per prerequisites.md — account is named for the provider, not the kind string); keyless kinds
  have no account and every read returns None. `read_key` is the full value's only reader path
  (called once, by a provider constructor); everything else goes through `masked_key`.
  `SecretFilter` drops any log record whose `getMessage()` contains a stored secret;
  `scrub_detail` applies the same predicate to `detail` and **drops rather than redacts** (a
  partial redaction leaks length/shape). keyring is stubbed in tests — the live Keychain path
  never runs in CI, only on a developer machine with the key stored (prerequisites.md).
- `state/`: `StateValue` is the flat five-field triple of Decision 7, `NullStateSource` returns
  an empty snapshot immediately. No behaviour to test here; the no-degradation guarantee is
  asserted in the phase-7 turn-pipeline tests.

## Conversation state (`conversation.py`)

- `Conversation` holds (question, answer) pairs for the last 6 **content-outcome** turns only —
  engine-determined outcomes (timeout, cancelled, incomplete, gates) never enter history and never
  touch the narrowing counter. There is deliberately nowhere to store a passage: 10.2/10.5 hold
  structurally (a test asserts no attribute name contains "passage").
- Carried scope is `{source_id: display_name}` — display names are captured at `set_scope` time
  because 5.11's `scope_dropped` reports a *removed* source, which the pruning view can no longer
  be asked for a name.
- 7.4 query assembly: `retrieval_query(q)` returns `f"{symptom_question} {q}"` only while
  `_awaiting_narrowing` (last content turn was needs-narrowing); `symptom_question` is pinned at
  the *first* narrowing turn of a run, so a second narrowing answer still carries the original
  symptom, not the intermediate answer.
- `ConversationStore.get(None)` mints a uuid; an unknown id creates a fresh conversation under
  that id (the honest post-restart reading of 10.7 — a stale id simply starts over).

## Turn pipeline (`turn.py`)

- `TurnPipeline.turn()` is a **sync** method returning the async generator: the supersede signal
  for 9.13 is sent at call time, not at first read, so an in-flight turn is cancelled the moment
  the new question arrives. `_inflight` maps conversation id → `_Handle(supersede, finished,
  started)`; the new turn awaits the old handle's `finished` only when `started` (a never-pulled
  generator would deadlock the wait; it emits cancelled+done whenever finally read).
- Streaming loop: per delta, `asyncio.wait({anext_task, supersede_wait}, timeout=watchdog-if-no-
  first-token)`. On supersede/watchdog the anext task is cancelled *and awaited* before
  `stream.aclose()` — aclose on a generator with an in-flight anext raises RuntimeError. Cancelling
  the anext task finalises the provider generator (its `finally` runs), which is what makes the
  250 ms release a close-not-drain.
- Event emission is incremental on the parsed path only: outcome after line 1, direct_answer after
  line 2, `body_delta` per body line via `FramingParser(on_body_line=...)` (a phase-7 addition —
  the callback fires for body-bound lines only, never hoisted sigils, so envelope fields cannot
  leak into deltas). The unparsed path emits everything at close (outcome from coverage, raw text
  as one body_delta) — the honest degradation for a provider that ignored the framing.
- Delta marker-stripping uses a local `_clean_delta` (marker removal only, no whitespace
  collapse) — `ground.strip_unknown` collapses/strips whitespace, which would destroy a caveat
  continuation's two-space indent and re-type the block client-side.
- Abnormal terminations re-emit `outcome` (cancelled: outcome+done; failures: outcome+timings+
  done) — the design names this shape explicitly for 9.13 ("emits outcome: cancelled then done"),
  so §4b's "outcome precedes every other event" describes the normal shape only.
- On ranked-causes the engine back-fills `citations[]` for every `cites[]`/`fix_cites[]` id the
  model didn't cite, rebuilding the entry citation with `unbacked_for_turn=True` when any cause
  has empty `fix_cites` (one citation record per passage — last write wins on the unbacked mark).
- 8.8's "note that state was unavailable" has **no envelope field or §4b event** (closed set), so
  it is logged at INFO on `dawmans.answer.turn` — carries the fault only, never question text
  (9.11). Tests assert via caplog.
- Timings: retrieval/state measured inside their gather members; `engine_overhead_ms = total −
  gather_wall − provider_time`, clamped ≥ 0; `completion_ms` absent on failed turns;
  `corpus_reload_ms` read off the watcher (run-level).
- Test trap: a `ScriptedProvider(endless=True)` bound to the pipeline serves *every* turn — a
  "new question cancels old turn" test must switch the binding to a finite provider before the
  second turn or `collect()` never terminates.

## The local HTTP surface (`http/guard.py`, `http/app.py`)

- `guard.py`: `ensure_loopback_bind` raises `SystemExit` with a string (exit status 1) naming the
  address and the constraint — addresses only, so `localhost` (a resolvable name) is refused as a
  *bind* even though it is accepted as a *Host*. `HostOriginGuard` is pure ASGI, port-derived sets:
  Hosts `{127.0.0.1, localhost, [::1]}:port`, Origins `http://` + the same. Absent Origin passes;
  `null` and cross-port loopback (the Vite dev server) are 403 `{"rejected": ..., host/origin}` —
  machine-readable, no `outcome` field.
- `create_app(watcher, port, registry=None, secrets=..., manuals_root=None, pipeline=None,
  static_dir=None)` registers each route group only when its component is supplied, so phase-8
  tests drive slices; the phase-9 serve wiring supplies everything. Static mount is last so API
  routes win.
- `ProviderRegistry` (in `app.py`): mutable selection the routes write and a turn reads once via
  `binding()` (6.3). `factory(kind, model) -> Provider | None` — None means unconstructable
  (keyed kind, no stored key), which pre-flight maps to provider-unconfigured/missing-credential.
  `select()` returns False (recording *nothing*) for shared-backend without `disclosure_ack`;
  with the ack it also calls the instance's `acknowledge()` so the provider's own defence-in-depth
  gate matches the registry. `refresh()` re-constructs the keyed provider after a credential
  change. Credential routes always operate on KEYED_HOSTED — the only keyed kind.
- GET /sources reports `manifest_fault` as a **fixed notice**, never the raw `ViewLoadError`
  string — that string embeds the manifest path and no filesystem path may appear in any payload.
- serve-document: rebuilds `<vendor>_<product>_<doctype>_v<doc_version>_<lang>.pdf` (doc_version
  arrives stripped of its leading v), realpath-confines to the manuals root, `FileResponse`
  with `media_type="application/pdf"` and **no filename** (a filename adds a Content-Disposition,
  which downloads and defeats `#page=N`). Starlette's FileResponse handles Range natively.
- POST /turn: request-time validation (422 `{"rejected": "question-too-long", limit, received}`
  with no outcome — a request rejection, not a turn), then `pipeline.turn()` is called **in the
  handler**, so the 9.13 supersede fires at request time. Headers before the first body byte:
  `dawmans-turn-stream: dawmans/turn-stream/1` (9.15) and `dawmans-conversation-id` — the minted
  id has no other way to reach the caller (no §4b event carries it).
- SSE emitter: per-event payload mapping in `_event_payload` (asdict + drop-None for
  outcome/citation/timings/required_*; `{text}` wrappers for deltas; `done` passes through
  `{"complete": true}`). StrEnums serialise as their values through `json.dumps` (str subclass).
- **Disconnect chain (9.10), three links all needed:** Starlette's `StreamingResponse` never
  finalises its body iterator, so `_TurnStreamResponse.__call__` acloses it in a finally; `_sse`'s
  finally acloses the pipeline generator; `TurnPipeline._run`'s finally acloses `_events` (async
  for never closes sub-iterators). And in `_events`' provider finally: an external close can land
  with an `anext` task in flight — `stream.aclose()` then raises "generator is already running"
  and was silently swallowed — so the fetch task is cancelled and awaited *before* aclose.
  Without any one link the provider is only released at GC.
- Test notes: httpx `ASGITransport` buffers the whole response, so incrementality and disconnect
  are tested by driving the raw ASGI app (capturing `http.response.body` messages as sent, receive
  returning `http.disconnect` on cue). `tests/answer/http_fixtures.py` holds the StubWatcher
  (swap-on-check + `manifest_fault`), the shared corpus fixture, the request helpers and
  `parse_sse`; passage ids in URLs need `quote(pid, safe="/")` for the `#`.

## Serve wiring, end-to-end and timing (`cli.py`, phase 9)

- `run_serve` on `dawmans/cli.py` (not a `dawmans.answer` module — design §Module placement is a
  closed list and names none). All serve-side imports are deferred into the functions: cli.py is
  shared with the future ingest commands, whose environment installs the `ingest` extra only, so a
  module-level starlette/fastembed import would break `dawmans --help` there.
- Startup order: loopback check **first of all** (a refusal must not cost the 7.2 s model load —
  the design only demands "before uvicorn.run"), then ViewWatcher (raises on a
  present-but-unreadable manifest; a *missing* manifest serves an empty corpus), then
  `load_model()` + one throwaway encode, then `run_server`. Both are injectable seams —
  `load_model() -> (embedder, count_tokens)` and `run_server(app, host, port)` — so
  `test_serve.py` asserts the order without the model or a socket; the view step is recorded by
  monkeypatching `dawmans.answer.view.ViewWatcher` (run_serve does the from-import at call time).
- `count_tokens` is `fastembed.TextEmbedding.token_count` — the resident BGE tokeniser, satisfying
  Decision 8's no-SDK-call rule. The tokeniser only loads with the onnx model, i.e. after the warm
  encode; the wiring order guarantees that.
- Provider factory: KEYED_HOSTED reads the key at construction and returns None without one
  (pre-flight maps that to missing-credential); LOCAL takes `--local-url` (default
  `http://127.0.0.1:8080`, llama.cpp — the provider appends `/v1/chat/completions` itself, so no
  `/v1` in the URL); SHARED_BACKEND is the stub. The 6.11 SecretFilter is installed on a
  `logging.basicConfig` handler here. Default port 8722; `--static-dir` defaults to `web/build`
  when present.
- `tests/answer/test_end_to_end.py` drives the full stack minus the socket: a real ViewWatcher
  over a disk index written by its `write_index` (view dir first, manifest last, explicit mtime
  bump), one-hot vectors + a settable stub embedder for exact cosine control, the guarded app,
  and per-turn `ScriptedProvider`s. Covers one turn per content outcome, the narrowing entry path
  run to the ranked-causes terminal, and the corpus swap (a removed source → `scope_dropped`;
  the last one removed → `no-sources-selected` — the third revision must still hold passages or
  the corpus-empty gate would fire first). `test_serve.py` imports its fixtures.
- `tests/answer/test_timing.py`: 4.2/4.3 in CI over an in-memory 1,200-chunk `make_view` (random
  unit vectors, generated vocabulary); the query embed is a stub there — the real ~2.2 ms embed
  is bench's. Overhead/retrieval/state each asserted against its own budget.
- `make bench` → `tools/bench.py`: skips honestly without `index/manifest.json` or the Keychain
  key. Measures first-token/completion p95 per provider class (narrowing question against the
  first-token target only, 7.3), estimates 4.1 as first token + 100 ms paint allowance, and
  calibrates Decision 8's 10% margin via `anthropic.Anthropic().messages.count_tokens` vs the BGE
  count. Exits 1 on a missed budget. Never run in CI, so keep it lint-clean by hand.

## Post-implementation spec review (2026-08-15)

A four-way requirements audit after phase 9 found and fixed four behaviour gaps, all now tested:

- **2.3** — the model-`!suggest` path resolved against *all* sources, so a `!suggest` naming an
  already-selected source reached `suggested_sources[]`. The engine now drops selected ids in the
  turn's merge (turn.py), same rule as an invented id.
- **7.6** — `direct_answer` on an entry-path `ranked-causes` turn streamed the model's line 2.
  It is now engine-built: `Check whether {rank-1 cause's check}.` replaces line 2 at drain time
  (`terminal_answer` threaded into `_drain`), and `parser.result` is `replace()`d so grounding and
  the conversation record match what streamed. The fallback (no-entry) path stays prompt-level: a
  line-2 direction added to `_TERMINAL_DIRECTION` — same enforcement tier the design accepts for
  7.5 there.
- **6.8** — the local provider mapped a 429 to `ProviderFailure("error")`. It now classifies
  `rate-limited`, parses `Retry-After` unrounded, and retries at most once ≤ 3 s before any
  output, mirroring the Anthropic provider. `RETRY_AFTER_CEILING_S` moved to provider/base.py
  (anthropic.py re-exports it; a test imports it from there).
- **6.7** — the unreachable result now names the provider in `detail`, matching the timeout path.

Known, deliberate gaps left as-is (each argued in design.md or vacuous under NullStateSource):
- **7.8** — `build_narrowing(state_supplies=…)` exists but the pipeline never passes a predicate:
  there is no defined mapping from `StateValue.key` to a candidate, and inventing a fuzzy match
  would silently remove candidates. Wire it when a real StateSource defines the mapping.
- **7.5** — prompt-only enforcement of the 2-question limit is the design's recorded choice
  (§The narrowing limit); a non-compliant model at the limit can still emit a third question.
- **2.7** — a model that frames `answered` over zero supplied passages is not overridden
  (Decision 3 keeps content outcomes model-chosen); the `ungrounded` signal is the backstop, and
  the empty-supplied path now has a pipeline test.
- **8.8** — "note that state was unavailable" is INFO-log-only; the §4b event set is closed
  (rationale in turn.py's module docstring). Needs a CONTRACTS event if it should reach the caller.
- **5.12** — device scope is deliberately wider than the requirement text when no vendor manual is
  selected (design §Device scope argues it; requirements.md was never amended, no decision-log
  entry). Spec-hygiene item, not a code defect.
- **needs-narrowing with <2 candidates** — a one-cause entry plus a model choosing
  `needs-narrowing` ends the turn with that outcome but no `narrowing` event; the outcome has
  already streamed by the time `build_narrowing` returns None.
