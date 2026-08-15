# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Template note.** Start logging under `[Unreleased]` from the first real change
> in the derived repo, then delete this note.

## [Unreleased]

### Added

- **A harness-neutral workflow for authoring triage entries from forum reading.**
  `docs/workflows/triage-from-threads.md` is the procedure; `tools/sections.py` (`make sections
  ARGS="…"`) prints paste-ready `fix:` pointers from the committed index so a section number is
  never written from memory. No product code and no spec change: the loop is `dawmans coverage` →
  read → look up sections → write the entry → `dawmans ingest` + `validate`, all of which already
  existed. A forum thread stays out of the corpus entirely — never fetched at answer time, ingested,
  cited or committed — so `data/symptom-triage`'s "a forum or community corpus" non-goal is
  untouched: it informs which documented control a human suspects, and the committed entry is the
  owner's, cited to the manuals. The `docs/workflows/` directory is new and referenced from
  `AGENTS.md`.

- **`README.md` now introduces the product.** It was a one-line stub. It now carries the product
  intro, the stack table, mermaid diagrams for the system, a turn and the ingestion run, a
  three-depth walk through the deployment patterns (the ingest/serve extras split, the loopback
  binding, the four-step startup order, provider selection as runtime state), and a table of every
  configuration surface with whether it is tracked.

- **`AGENTS.md` and `web/README.md` now describe this repository.** Both were unfilled template
  text. `AGENTS.md` claimed `build`, `test` and `clean` still error and that `make lint` runs only
  the spelling check — all three false since the stack landed — and documented a `nextup.md` entry
  point that does not exist here. It now carries the real commands, how to run a single test on
  either side, the setup steps that need network or the vendor PDFs, the AGPL confinement rule, the
  commit and branch conventions, and the fact that CI checks spelling and nothing else.
  `web/README.md` was the stock `sv` scaffold; it now documents the surface's own structure, the
  Origin-rewriting dev proxy, and the browser install the e2e suite needs.

### Fixed

- **Every compound term in the corpus was indexed and unreachable from any question.**
  `index/lexical.py::tokenise` keeps a compound whole *and* in parts — `Dry/Wet` indexes as
  `dry/wet`, `dry`, `wet` — so that model names, version strings and hyphenated/slashed tokens match
  exactly (`data/manual-corpus` 8.8). But `answer/retrieve.py::tokenize_query` called
  `bm25s.tokenize`, whose default splitter emits the parts only and needs two word characters, so no
  question ever produced `dry/wet`, `mid-side` or `re-enable`, and `no sound from track 3` did not
  match on `3`. The fragments still matched, so the cost was ranking signal rather than results and
  nothing failed — parity was asserted only over in-memory fixtures that tokenise both sides with
  the same function and so could not see them drift. `tokenize_query` now calls `tokenise` itself;
  the corpus owns the rule that produced its vocabulary, and a second implementation on the query
  side was the drift. Measured over the real 1,436-passage index, 6 of 10 benchmark questions changed
  their supplied passages — all compound- or numeral-bearing, with the prose controls unmoved — at
  no latency cost (median 1.10 → 1.06 ms, p95 1.51 → 1.47 ms, against 4.2's 10 ms / 50 ms).

- **Stale agent notes.** `web-surface.md` gave the dev proxy's default engine origin as
  `127.0.0.1:8000` (it is `8722`), described the `web/build` mount as future work and `dev-engine`
  as a placeholder echo, and left the turn-stream header's engine half open — the engine has sent
  `dawmans-turn-stream` since the HTTP surface landed. `answer-engine.md` still described the
  manual-corpus index build as not yet implemented.

- **The engine crashed on every turn citing a manual passage that carries a figure.**
  `Citation.has_figures` was modelled as a tuple of figure pages while `data/manual-corpus`
  publishes a bool and `ui/ask-and-source-picker` types the field `boolean`, so `build_citation`
  ran `tuple(True)` and the SSE stream died mid-turn with a 500. Four of the five starter symptoms
  failed this way the first time they were asked. The field is now the bool its only producer
  emits (`api/answer-engine` Decision 12). The crash was the visible half: an empty JS array is
  truthy, so a turn that did not crash would have marked every vendor citation as carrying a
  figure.

- **The ungrounded warning fired on every answer.** A model that numbers its sections `## 2.`
  produces a heading whose entire content is `2.`, which the numeric class read as a fact-shaped
  token in an uncited block — so all five starter symptoms came back flagged while every prose
  block in them was cited. A block with no letter in it is no longer fact-shaped
  (`api/answer-engine` Decision 13): a claim about a product is made in words. Real numeric claims
  (`0 dB`, `512 samples`) sit beside words and still fire arm (a).

- **The system prompt was read literally by a local model.** "Respond in the format
  dawmans/answer-framing/1" put that string on line 1 instead of an outcome token, so every turn
  degraded to the unparsed path — 0 of 3 measured, and telling the model never to print the name
  made it worse. The format is now named in a parenthetical after the structure, which measured 3
  of 3 parsed. Separately, the ordered-step marker written `N. ` was copied verbatim against a
  parser requiring `^(\d+)\.`, so every step arrived as a paragraph beginning "N.".

- **`make bench-answer` could not run against a local provider at all**, and lied when it failed.
  A provider's `httpx.AsyncClient` binds to the first event loop that uses it, so `asyncio.run` per
  question killed the second question with "Event loop is closed"; a provider's turns now share one
  loop. It also passed no model name, which any server hosting more than one answers with an error
  on every question — `--local-model` now supplies it. And a run where nothing reached synthesis
  printed "all budgets met"; an empty sample now fails.

### Changed

- **`make bench-retrieval`** measures 4.2 against the real index without a provider. The only
  real-corpus retrieval figure previously lived inside a turn that needed a Keychain key, so the
  budget a retrieval change actually moves was unmeasurable on a machine holding no key — which is
  how the tokeniser divergence above went unbenchmarked. It prints the tokens and the supplied
  passage ids per question, so a ranking change is readable and not merely present.

- **`data/symptom-triage` 7.7 is a real assertion.** The acceptance test asked nothing: it was
  written while `api/answer-engine` had no implementation and stood as a skip reading "wire this to
  POST /turn" through that spec's entire build. It now asks the five starter symptoms through
  `TurnPipeline` over the committed view and fails on a refusal. Running it for the first time is
  what found the two engine defects above. It passes: five of five answered, none refused, against
  the four real manuals and a 20B model served over loopback.

- `SPOUT.md` is now gitignored as a generated output artifact.

### Added

- **`data/symptom-triage` Phase 7 — the starter set, and the acceptance and timing targets.**
  `triage/` now holds the five committed entries of 7.2–7.6: no sound from a track, a track is
  distorting, latency when monitoring, a drum pad triggers the wrong sound, and the controller does
  nothing. Every cause carries an observable check and a fix pointer into a vendor manual, every
  pointer resolves against the real index, and 2.3's carve-out is used nowhere — all four manuals are
  ingested, so 7.8 admits no exception. The distortion entry carries 7.3's elimination step as an
  ordinary ranked cause naming Saturator, Drum Buss, Overdrive, Vinyl Distortion, Dynamic Tube and
  Amp, so an answer does not offer a distortion device as the cause of unwanted distortion.

- **A fourth section fixture, `alesis_sections.json`.** 7.5's General MIDI and channel causes are
  documented by the Nitro Max and by nothing else; citing Live's Drum Rack section instead would
  resolve and would pass the term check while pointing at a different control. The fixture is cut by
  the same tool as the others, and `tests/triage/test_starter_set.py` asserts the cited `source_id`
  rather than only the resolution.

- **The acceptance and timing targets** (`tests/triage/test_acceptance.py`). 5.6's budget is measured
  over a synthetic 200-entry store — ingested and validated, with all 400 pointers re-checked, inside
  5 seconds warm. The cold deviation stands as designed and is asserted structurally rather than
  hidden in the budget: `dawmans ingest` loads the embedding model before it reaches any loader, so
  an authored-only run still pays it. 7.7 needs `api/answer-engine`, which has no implementation, so
  its end-to-end half skips under `make bench` naming what it waits on, while its corpus-side
  precondition — the five entries in the committed view with their devices, causes and citations —
  runs.

- **`data/symptom-triage` Phase 6 — validation messages, `dawmans validate` over the store and
  `dawmans coverage`.** `triage/messages.py` renders a rejection or a flag as the design prints it:
  a header naming the file and the symptom, then the prose saying what is wrong and what to change
  in the entry's own words (5.3). A reason constant never reaches the author — `rejected:` against
  `flagged:` is the whole difference on screen between an entry withdrawn and an entry served with a
  remark. The counts line is 5.5, over entries rather than passages, and a missing ledger says so in
  one line rather than letting a wall of 2.2 rejections arrive unexplained. One malformed fixture per
  reason constant pins the taxonomy closed at the fifteen of design §Error Handling, with two
  well-formed entries beside them proving a rejection costs one entry and not the run (5.2).

- **`dawmans validate` now validates the entry store** (5.4). It parses, resolves and term-checks the
  whole store against the committed view — read through `manifest.view_dir` by `CorpusView.read`, the
  same reader the ingest path uses over shards — and **writes nothing**: no index write, no shard, no
  ledger row, no embedding model loaded, asserted by snapshotting the whole tree either side of a
  run. A term miss exits non-zero here and never under ingest (Decision 5): consequences where the
  author is, none where the user is.

- **`dawmans coverage` — the §6 report.** Six row sets over one evaluation of the store: every entry
  with its scope, cause count and pointer health (6.1); every rejection and flag with its reason, so
  the report covers 100% of the store (6.2); every rig device no entry declares scope for (6.3);
  every cause 2.3 permits to carry no pointer, with the device it names (6.4); every drifted pointer
  with the source that changed (8.6); and every entry scoped only to gear the rig no longer holds
  (8.7), reported and never deleted. **No percentage anywhere** — there is no denominator over
  symptoms. The same rows land in the sidecar's `report` block, so the report is obtainable without
  asking a question (6.5) and published where a consumer can read it (6.6's publishing half).

- **`data/symptom-triage` Decision 14 — `dawmans validate` exits non-zero on a rejection**, not only
  on a term miss. 5.2's "the run reports succeeded" governs the *ingestion* run, which still serves
  the other entries; `validate` serves nothing and is asked one question, and answering "yes" while
  printing an entry that will not be served is the one answer it must not give. Flags do not fail it:
  `pointer-drifted` and `unbacked-cause` are states the design chose over withdrawing working triage.

- **`data/symptom-triage` Decision 15 — 8.7's orphaned scope is a coverage row, not a flag.** The
  design listed `orphaned-scope` among the flags while its own §Device scope table forbids flagging
  the device such an entry declares — a documented device absent from `rig.yaml` is gear removed under
  8.7 *or* a manual added ahead of its rig entry. The entry-level fact is reported in the coverage
  report instead, per entry rather than per device, and an empty rig inventory declares no removal at
  all. The flag list is marked superseded in place.

### Fixed

- **`data/symptom-triage`: the flagged count now includes parse flags.** `report()`'s `flagged`
  counted entries carrying evaluation flags, so an entry whose only remark was
  `unknown-frontmatter-key` or `closing-statement-inferred` — both raised before any entry outcome
  exists — was reported as unflagged while its row was printed beneath the count. Counted by file
  over the store's flags, which also keeps an entry with three remarks one entry to look at.

- **`data/symptom-triage`: `undocumented-claim-invalid` names its cause in the message.** The record
  carried the cause and the prose did not, so the one rejection an author meets while taking 2.3's
  carve-out named the file and the symptom but never the cause concerned (5.3).

- **`data/symptom-triage` Phase 5 — discovery, the sidecar and the run integration.** `dawmans
  ingest` now runs both stores with the real `TriageLoader`. Discovery is a recursive scan of
  `triage/**/*.md` (1.6): a subdirectory entry is found, a non-`.md` file beside one gets a report
  line — the opposite of `manuals/`, where the skip is silent — and dotfiles are exempt so the
  machine's own `.pointer-ledger.jsonl` never warns about itself. The store is one source however
  many files it holds, and its fingerprint is sha256 over the sorted (store-relative path, file
  digest) pairs. `load()` runs on **every** ingest regardless of that fingerprint, because 2.1 asks
  for every fix pointer to be re-checked on every run and a digest of the store's own bytes cannot
  answer a question about the manuals. An absent or unreadable store is an unknown discovery set
  that removes nothing; an existing empty one removes its shard; a store in which no entry survives
  is `authored-invalid`, which deletes the shard rather than letting the previous run's passages
  keep being served.

- **The per-`passage_id` sidecar (`triage/scope.py`).** `LoadResult.sidecar` lands at
  `views/<hex>/reports/authored_triage.json` — the corpus's slug rule, underscore and not hyphen,
  inside the view so it swaps atomically with the passages it keys. Each row carries the entry's
  declared devices (4.3, the input to `api/answer-engine` 5.13's per-passage predicate), the
  `source_file` and `line` halves of CONTRACTS §2 `entry_location`, an `entry_key` annotation, and
  the causes in declared order with their checks, resolved fix passage ids and flags — the source of
  CONTRACTS §4c's `Cause` records. Every passage of a split entry carries the whole cause list,
  because which passage holds which cause is an artefact of the 350-word cap. The report block
  carries 2.8's pointer counts and one row per rejection and per flag with its reason (5.5), and is
  written to `index/audits/authored_triage.json` as well so a rejected store's reasons survive.

- **The term check and `title-number-disagreement` joined the run.** `CorpusView` now carries
  passage text, so `check_terms` runs during evaluation and a factual claim no cited section prints
  is flagged (2.6) — never setting `unbacked`, which keeps 2.4 and 8.5 its only two producers
  (Decision 5). A view read without passage text checks nothing rather than flagging everything.

- **The pointer ledger is written by the run.** `load()` records every pointer that resolved and
  writes only on transition, so a second run over an unchanged store leaves
  `triage/.pointer-ledger.jsonl` byte-identical and the working tree clean. Recording happens in
  `load()` alone, which is what will let `dawmans validate` run the same checks without promoting a
  broken pointer to "previously fine" (5.4). An unparseable ledger reaches the run as a failure:
  non-zero exit, previous shard intact.

- **`data/symptom-triage` Decision 13 — the run's `CorpusView` is read from the committed shards,
  not the committed view.** The design required both "the authored load runs after every vendor
  shard has committed" and "`CorpusView` never opens a shard", and `manual-corpus` merges shards
  into a view only at the end of a run — so at authored-load time the view named by
  `manifest.view_dir` is the *previous* run's. Reading it would reject a new entry pointing into a
  manual the same run ingested, and would detect drift one run late. The shards hold the passages
  the merge concatenates, so 5.7 is untouched: no PDF, no vector file, no extraction, chunking or
  embedding. `CorpusView.of` takes the published JSON shapes, so `dawmans validate` will read the
  same rows out of `views/<hex>/` with no second reader. The design's `CorpusView` row is marked
  superseded in place.

- **`data/symptom-triage` Phase 4 — identity, emission and the loader.** `triage/loader.py` puts the
  entry store behind `manual-corpus`'s `SourceLoader` seam. `source_record` is design §Identity's
  table applied literally — the constant `authored/triage`, `My Triage Notes`, `assumed`
  applicability that nothing in configuration can raise, and not one of the seven vendor-manual
  fields, which 12.5's constructor refuses rather than defaults. `emit` turns one entry into one
  `Region`: the symptom, its `also:` phrasings and its preamble first as a `repeat_on_split` unit,
  then each cause `atomic` in declared order (1.5 — that order becomes CONTRACTS §4c's rank), then
  the closing statement. `passage_id` is minted by the corpus chunker and nowhere else, so an
  authored passage is identified by the same function over the same canonical form as a manual
  passage (3.9); `parse.render_blocks` is the one construction of that form, joined with a blank
  line for the reader and with `UNIT_JOIN` by the chunker, which hash alike because `passage_id`
  collapses whitespace before hashing.

- **`data/symptom-triage` Decision 12 — the authored overlap suppression is `manual-corpus`'s rule,
  not an edit here.** Task 16 reserved a keyed change to `dawmans/corpus/chunk.py` as the one edit
  this spec makes to the chunking pipeline. That edit has since been made upstream and made more
  general: `manual-corpus` Decision 15 states it as "a repeat replaces overlap rather than joining
  it", which reaches the authored case without the chunker knowing what kind of source it has
  (12.2). Making it again would be two rules that must agree in one function. The outcome is
  asserted from this spec instead — `Chunk.carried` equals the symptom block's word count on every
  continuation — so a relaxation upstream fails a test here rather than quietly putting the symptom
  into hashed, user-visible text twice.

- **`data/symptom-triage` Decision 11 — canonical idempotence is stated over a parse–rebuild round
  trip.** Task 13's literal `render(parse(render(parse(f)))) == render(parse(f))` cannot hold:
  `render` excludes the frontmatter, the fix pointers and the filename by design, so its output is
  not an entry file and the inner parse rejects with `frontmatter-missing`. `render ∘ parse ∘
  rebuild` is asserted instead, `rebuild` being a test-support writer that re-supplies exactly what
  the rendering drops — which keeps the property passing through the real parser and the real
  rendering without shipping a second definition of the entry format.

- **`data/symptom-triage` Phase 3 — the term check.** `triage/terms.py` implements design §The term
  check (2.6): extraction over the cause statement plus its `check:` value and nothing else — the
  deliberate narrowing that keeps 2.5's causal assertions out of a factual check — of capitalised
  runs and numeric literals, and containment against the passages the cause's pointers resolve to.
  Containment is case-sensitive at word boundaries for the capitalised class, because casefolding
  would make `Off`, `Monitor` and `MIDI` match almost any prose, and casefolded for numerics,
  because unit case varies between manuals; `0` never satisfies `10`. Any one pointer's resolution
  set satisfies a term, and a split section is seen as its concatenation. A miss is a
  `term-not-in-passage` flag naming the term and the section and never sets `unbacked` (Decision 5)
  — 2.4 and 8.5 stay the only two producers of that mark. Phase 3 is now complete: scope validation
  landed with tasks 11–12.

- **`data/symptom-triage` Decision 10 — a sentence-initial capital is discounted per token, not per
  run.** The design states the rule for a single-token run at a sentence start. Applied literally,
  an author writing the design's own worked example — "The Track Activator is off" — yields the term
  `The Track Activator`, which is in no manual, so the example flags and §Testing Strategy's
  term-check soundness property breaks for any statement opening with an article. Discounting the
  token before runs are formed yields `Track Activator`, leaves every case the design names
  unchanged (`Live` alone still drops; `DIRECT MONITOR` still stands, ALL-CAPS being evidence a
  sentence start does not explain), and keeps one justification covering both cases.

- **`data/symptom-triage` Phase 2 — pointer resolution and the ledger.** `SectionIndex` builds the
  two maps of design §Fix pointers in one pass over a view's `passages.jsonl`, and `resolve` returns
  a section's passage ids in section order or an `Unresolved` naming why, with nearest-section
  candidates for the 5.3 message. Reading passages and nothing else is what makes 8.3 hold:
  `doc_version` lives on the `SourceRecord`, so a new document version of the same passages cannot
  move a pointer. `pointers.Ledger` is the committed NDJSON memory that separates 2.2's rejection
  from 8.4's flag — keyed on the pointer alone (Decision 4), sorted, never pruned, and written only
  on transition so an unchanged run leaves the file byte-identical. `.gitattributes` sets
  `merge=union` on it.

- **The section fixtures, cut from a real index.** `tests/fixtures/sections/` holds the 21 Live
  sections the starter set points at (including §18.1.1, which prints the `0 dB` requirement 7.3
  depends on), the Scarlett's Direct Monitor sections, the APC guide's unnumbered regions, §28.24
  chunked into three, and the `drift/` before-and-after pair. They are slices of a view built once
  locally by `tools/extract_section_fixtures.py` and committed, so the suite runs with `manuals/`
  absent and no embedding model loaded — the arrangement `data/manual-corpus` already uses for its
  extraction snapshots. `tests/fixtures/README.md` documents each; it sits above both fixture roots
  because every `.md` file under an entry store is an entry, so a README beside one would be
  discovered and rejected as a malformed entry.

- **`tools/check_spelling.sh` skips `tests/fixtures/`.** Those files quote the vendor's own words
  verbatim so a stage can be tested against what the manual actually says; correcting a manual's
  spelling would make the fixture a document nobody shipped. `orbit-impl-1/manual-corpus` already
  carries the identical exclusion for the identical reason, so the two copies agree rather than
  conflicting on merge.

- **`data/symptom-triage` Decision 9 — a ledger transition is detected by comparing passage ids.**
  The design requires `resolved_at` move only on transition but does not say how a run recognises
  "resolution after a drift", and the ledger deliberately carries no drifted marker. Comparing the
  row's `passage_ids` against what the pointer resolves to now settles it from the row itself: a
  renumbered, rewritten section produces different passages, while a manual restored to exactly its
  previous state produces the previous ids and so writes nothing at all.

### Changed

- **`normalised_symptom` and a new `entry_key` moved to `triage/model.py`.** Both are functions of
  the model's own fields, and `loader` needs the first for 1.9's duplicate test while `scope` needs
  the second for the sidecar — with `loader` importing `scope`, `model` is the only home that is not
  a cycle. `loader` still re-exports `normalised_symptom`. `scope.RigDevice` gained `display_name`,
  which the term check reads, so the protocol states what this spec reads of a rig device rather
  than what one module does.

- **A rejected entry's flags no longer appear in the run's flag list.** Parse flags are collected
  before anything can reject an entry, so an entry excluded for being malformed was contributing
  remarks beside the reason it went. They are dropped, which also keeps the report's `flagged` count
  and its `flags` rows describing the same entries.

- **The triage tests share one store builder.** `tests/triage/stores.py` holds the on-disk store,
  the `CorpusView` over the committed section fixtures and the loader that reads them, extracted
  from `test_emission.py` when the discovery and sidecar tests needed the same fixtures.
  `tests/triage/test_ingest_wiring.py` runs the real loader through `cli.ingest` with a stub vendor
  store rebuilt from those same fixtures; `tests/test_run.py` deliberately keeps a *stub* authored
  store, because a run that only ever saw the real one would prove nothing about 12.2.

- **Costed the `data/manual-corpus` merge that unblocks `data/symptom-triage` Phase 4.**
  `docs/agent-notes/triage-entry-grammar.md` said Phase 4 becomes reachable when that branch merges,
  but not that the merge is already available: everything Phase 4 needs — `SourceRecord` and
  `passage_id` — is committed at `4f0ea7c`, and the work still uncommitted in that worktree is all
  under `index/`, which Phase 4 never touches. The note now records that `git merge-tree` reports
  seven conflicting files, all of them the shared scaffolding the two branches grew independently
  (`.gitignore`, `CHANGELOG.md`, `Makefile`, `pyproject.toml`, `specs/OVERVIEW.md`,
  `src/dawmans/__init__.py`, `uv.lock`) with no semantic clash among them, and two already ruled by
  PROCESS.md §9. Phase 4 is therefore blocked on a decision about what belongs on this branch, not
  on a missing artefact — worth settling once instead of re-deriving each run. Phase 2 is unaffected:
  its two prerequisites are human-only.

- **Corrected the `data/symptom-triage` blocked-work note.** `docs/agent-notes/triage-entry-grammar.md`
  claimed `data/manual-corpus` was complete only through its task 17 and that no chunker or
  passage-id scheme existed; both now exist. The note names the real gate for Phase 2 — a committed
  `views/<hex>/passages.jsonl` from that spec's task 37, plus its human prerequisites — rather than a
  task count that goes stale, and records that Phase 4 is blocked too even though `rune` reports its
  first task ready: cross-spec dependencies are not expressible in the ledger, and every remaining
  task in this spec has one.

### Added

- **`data/symptom-triage` device scope validation (tasks 11–12).** `dawmans.triage.scope` applies the
  six rows of the design's Device scope table: a declared device in the rig inventory with no
  ingested manual scopes and reports `undocumented-device-scope` (4.4); one the corpus documents but
  the rig does not scopes silently, because 4.5's condition is "neither"; an unrecognised identity
  flags `unknown-device` and still ingests, unless *every* declared device is unrecognised, which is
  the `all-devices-unrecognised` rejection — the recorded deviation from 4.5, since a flag would
  leave the entry embedded and reachable by no turn. Identities are matched exactly (4.2), and
  `@revision` is compared after casefolding and stripping non-alphanumerics, quoting the rig's value
  verbatim on a mismatch (4.6). The 2.3 `undocumented:` claim rejects where it names a device absent
  from the rig, or one the corpus documents. Recorded as Decision 8: "indexed" means every identity
  the corpus documents — source ids **and** the device ids they declare under
  `source_applicability` — not source ids alone, or today's `focusrite/scarlett-solo` declaration
  would be reported as undocumented while its guide sits in the corpus.
- **`data/symptom-triage` Phase 1 — the entry model and the entry grammar.** `dawmans.triage.model`
  holds the frozen `Entry`, `Cause`, `DeviceRef`, `Pointer` and `Unresolved` records of the design's
  Components and Interfaces, together with the closed rejection and flag vocabularies of its Error
  Handling section. `dawmans.triage.parse` reads an entry file into an `Entry` and produces the
  canonical rendering: strict about the frontmatter, forgiving in the body, and **total** — every
  byte string yields an entry or a rejection naming the file, and never a half-built entry.
  `dawmans.triage.pointers` carries the fix-pointer grammar the parser needs; its `SectionIndex` and
  resolution are Phase 2.
- **The Python package, cut to what Phase 1 needs.** `pyproject.toml` with a `src/` layout, uv for
  dependencies, and pytest + hypothesis + ruff for development; `make test`, `make lint` and
  `make format` replace three of the unconfigured targets. The full scaffold — the whole module
  tree, `fetch-model`, `bench`, and the PyMuPDF confinement rule — remains `data/manual-corpus`
  task 1.

- **The rig inventory and the two gap reports** (`dawmans/corpus/rig.py`, `rig.yaml`,
  `data/manual-corpus` phase 8, requirements 11.1-11.7). `rig.yaml` is hand-maintained and
  committed — it says what the owner **holds**, while `manuals/` says what is **documented**, and
  11.3 keeps them apart on purpose. The join runs through `hardware_applicability.device` and never
  through `source_id` (Decision 9), which looks like a nicety until the Focusrite: the filename's
  product carries the generation marker (`scarlett-solo-4g`) and the rig's device id does not
  (`scarlett-solo`), so a join on the ID would report the device undocumented with its manual
  sitting in `manuals/`. `gaps.json` carries owned-but-undocumented and documented-but-unconfirmed,
  **both members always present even when empty** (11.4) — a consumer distinguishing absent from
  empty breaks on the day it fills. indexed-but-not-owned (11.7) stays in the run report and out of
  `gaps.json`: a manual for gear the owner does not hold is not a gap in the rig, and CONTRACTS §5
  governs two reports rather than three.
- **The per-run report and the per-source ingestion audits** (`dawmans/report.py`, 1.5-1.7, 4.4,
  5.4, 9.1, 9.5, 11.7). Every source is reported as ingested, skipped as unchanged, or rejected with
  its reason — and for a malformed filename, the pattern it should have matched. The six rejection
  reasons are closed **at construction** rather than checked at rendering: a rejection reports the
  run as succeeded, so a disk error dressed as one is a run that indexed nothing and exited zero,
  which is exactly what 1.7's failure path exists to prevent. The audit at `index/audits/<slug>.json`
  is written as each source finishes, committed shard or rejection, and always carries a `rejection`
  key — `null` where there is none, because absent and null are different to a reader. The 9.1
  inventory derives its fields from `SourceRecord` itself rather than a hand-written list, so it
  cannot drift from the CONTRACTS §1 table it is required to reproduce.
- **`dawmans ingest`, `dawmans validate`, `dawmans inventory`** (`dawmans/cli.py`, 8.6, 9.1, 9.6,
  12.2, 12.7). The whole stage order behind one command: collect superseded views, discover both
  stores, load the embedding model once, ingest the vendor sources and commit their shards, then the
  authored load, then the merge, `gaps.json` and the manifest rename. The vendor and authored
  loaders are separate parameters rather than a list, because their order is a constraint and not a
  convention — `TriageLoader` resolves each fix pointer against a vendor passage, so loading it
  earlier would resolve against the *previous* run's text. A rejection deletes the source's shard,
  since 1.6's "exclude that source from the index" is the passages going rather than a line in a
  report; a failure keeps the previous shard, is collected, and the run continues to the next source
  with no abort-on-first-failure path. Against the real corpus: 4 sources, 1431 passages, a full
  cold rebuild in ~43 s.
- **The timing tests and the `bench` target** (`tests/test_timing.py`, 8.1, 8.2, 8.4). 8.2 and 8.4
  run in CI against synthetic PDFs generated at test time; 8.1 needs the gitignored manuals and runs
  under `make bench`. 8.4 is measured with the model **resident**, exactly as the CLI arranges it,
  and the cold load is asserted separately in a fresh process and through to a first vector —
  `fastembed` builds no ONNX session until something is embedded, so a test that stopped at
  construction would time an import and pass however slow the real load became.

### Changed

- **The rig is joined at the merge, not written into the shard** (Decision 18). A shard is a cache
  of what the *document* said, keyed by the document's bytes; `rig.yaml` is what the *owner* says,
  and editing it changes no byte of any PDF. Applied at shard-build time, a new
  `source_applicability` declaration was invisible until something unrelated changed the manual —
  every cache key still matched, no loader ran, and the reports kept describing the last rig the
  corpus happened to be rebuilt under. Found by running the real corpus and seeing the Focusrite
  reported under owned-but-undocumented *and* indexed-but-not-owned at once, which is the pairing
  11.7 uses to signal a missing declaration that was not missing.
- **The authored store is exempt from fingerprint-based shard skipping**, per
  `data/symptom-triage` §Discovery. Its validity is a function of the manuals as well as its own
  text, so a fingerprint over its own bytes cannot say whether a fix pointer still resolves;
  skipping it left `unbacked` describing the run before last.
- `pytest` now runs with `-m 'not bench'` by default. The marker alone deselected nothing, so
  `make test` was running the full-corpus 8.1 benchmark.
- `AUDIT_DIR` is declared once, in `corpus/discover.py`. It had been defined in two modules and
  hardcoded in a third.

### Fixed

- `Rejection` now refuses a reason outside requirement 1.6's closed set. The `Literal` type
  documented the set; nothing enforced it at runtime.

### Added

- **The embedding wrapper and its offline pin** (`dawmans/index/embed.py`, `data/manual-corpus`
  phase 7). `fastembed` is the only network-capable dependency in the package, so ingestion pins
  `HF_HUB_OFFLINE=1` in its **own process environment** — not as a library argument — and then
  checks the `models/` cache, in that order: pinning afterwards would leave a run that recovered
  from the failure able to reach the network next time. An absent cache raises a **failure**, not a
  rejection (1.6's list has no member for it: no source is at fault and nothing can be embedded),
  naming the model, the directory and `make fetch-model`. The model is loaded **once per run** and
  passed to the shard build, because the ~7.2 s cold load against 8.4's 10 s budget for a whole new
  source leaves nothing if it is paid per source. The wrapper owns float32, 384-wide and
  L2-normalised output and rejects a backend of another width — vectors from a second model reaching
  the view under a manifest declaring 384 change nothing about the on-disk shape, so `index_version`
  cannot catch it.
- **The lexical index and its tokeniser** (`dawmans/index/lexical.py`, requirement 8.8,
  Decision 2). A `bm25s` index over the same passage ordering as the dense one, so document `i`,
  row `i` and line `i` are one passage. The tokeniser keeps a compound **whole and then in parts** —
  `Dry/Wet` yields `dry/wet`, `dry`, `wet` — which is the failure Decision 2 names and the one that
  is otherwise silent: a default tokeniser drops the compound, nothing errors, and the query a user
  is most confident about stops working. The tests assert the default *does* lose `Dry/Wet`,
  `4th-gen` and `bge-small-en-v1.5` before asserting ours keeps them, so a regression to the default
  cannot pass. No stopword list is applied: `bm25s`'s English list holds `on` but not `off`, which
  would make one half of every On/Off control unretrievable and leave the other.
- **The per-source shard and its four-part cache key** (`dawmans/index/build.py`, 8.3, 8.7, 9.3,
  9.4). A shard is reused only when **all four** of fingerprint, `ingestion_version`,
  `embedding.model` and `embedding.dim` match. Both failures the fingerprint alone allows are
  asserted, and both are silent: changing the embedding model would concatenate vectors from two
  models under a manifest declaring one, and a fix to table assembly or chunking changes no PDF byte
  and would reach nothing. The authored shard carries a `passage_id` → row map so editing one entry
  re-embeds that entry alone, while the shard is still rewritten wholesale (9.4). Artefacts are
  written to `.tmp` beside their destinations and moved with `os.replace`, **meta last**, so a
  partly committed set reads as no shard; a failed source's temporaries are deleted, its previous
  shard is untouched, and a source that succeeded in the same run stays queryable.
- **The merge, the manifest and the atomic view commit** (`dawmans/index/build.py`,
  `dawmans/index/manifest.py`, 8.6, 8.8–8.11, 9.6, 11.6, 12.7). The view is a plain concatenation of
  the committed shards **sorted by `source_id`** — filesystem order could otherwise shift
  `row_start` offsets between two runs over an identical source set while `corpus_revision`, hashed
  over sorted triples, stayed the same, leaving a consumer slicing the wrong rows. It is built into
  a directory no reader can be holding and `manifest.json` is renamed into place last, so that
  rename is the only switch; superseded views are collected at the **start** of the next run, so a
  reader working from the previous manifest keeps its files. Each shard's sidecar is copied into
  `views/<hex>/reports/<slug>.json` — a reused shard runs no loader, so a sidecar written only by
  `load()` would be absent from every later view — while ingestion audits stay outside the views,
  which is the two lifetimes the split exists for. A reader whose `index_version` differs refuses
  to load rather than interpreting the files.
- **The incremental-equivalence property** (`tests/test_incremental_equivalence.py`). A random
  add/edit/remove script over a random source set, one ingestion per step, must produce the same
  `passages.jsonl` bytes and the same `vectors.npy` rows as a full rebuild of the final state. This
  is the test that catches an incremental path quietly diverging from the rebuild it is supposed to
  be an optimisation of — a class of fault that produces no error, only a wrong index, and which
  every single-run test is blind to.
- **Passage identity** (`dawmans/corpus/passage_id.py`, `data/manual-corpus` phase 6). The digest
  covers the chunk's body text and nothing else (6.1, Decision 5), with `source_id` carried as a
  visible prefix rather than hashed, so cross-source collisions are impossible by construction and a
  fetch routes on the prefix without a lookup. Whitespace and Unicode composition are normalised
  away — a re-extraction differing only in line wrapping must not orphan every citation in the
  retained UI history at once — and case is kept, because two chunks differing only in case are
  different text. Where chunks share a digest the **first in document order keeps the unsuffixed
  identifier**; suffixing all of them would destroy the stable identifier of a copy whose text did
  not change. Determinism is asserted end to end over the same PDF bytes, not by re-hashing one
  string.
- **The chunker and the citation header** (`dawmans/corpus/chunk.py`). Greedy packing to the
  350-word cap within one region, so no chunk spans two sections (6.7) and the blast radius of a
  vendor edit stays inside one. Pages come from the chunk's **own** units, so a split table's
  continuation chunk records p26 rather than the p25 of the heading copied onto it (6.8); flags are
  the OR over every unit it holds, copied ones included, so a chunk of degraded rows stays degraded
  under a clean heading (5.3). An atomic unit that fits is never split (6.10, 7.4), one that does
  not is split with every part marked, and a split table repeats its joined heading — its own, never
  a previous table's (7.5). The citation header is embedded and BM25-indexed but is never part of
  `Passage.text`, and the section marker is omitted entirely rather than rendered as `§None`. A
  chunk page outside the source's range is a **failure**, not a rejection (6.11), and the check is
  skipped for a pageless source (12.8).
- **Sectioning, layout and region assembly** (`dawmans/corpus/pdf/`, `data/manual-corpus` phase 5).
  The stages that turn an annotated span model into the shared `Region[]`/`Unit[]` shape.
  `sections.py` builds the section map from the document's own structure — embedded outline, printed
  contents page, then heading styles, in that order and none of it per-manual configuration (6.6) —
  and anchors each entry to the line its heading is printed on, so a page shared by two sections
  splits between them rather than being attributed whole to one of them. Path C's quality gate fails
  closed, because a title plus a strapline clearing a naive test yields two regions spanning 1009
  pages and a wrong section on every citation inside them. A region carries its nearest two
  ancestors, so `§28.21.1 Sidechain Parameters` — one of eight in Live's TOC — renders under the
  device that owns it.
- **Row, column and table assembly** (`dawmans/corpus/pdf/layout.py`). Rows cluster by y, columns by
  x0, and every cell is placed by its horizontal position rather than by its index in the row (7.1,
  7.6): Nitro Max p25 prints two ragged panels of 11 and 8 rows, and index placement mis-pairs the
  tail. A heading printed across three physical lines is joined per column into
  `Trigger | MIDI Note Number | Trigger | MIDI Note Number`; panel boundaries come from that repeated
  heading sequence and never from a hardcoded x; and the page is never de-interleaved into per-panel
  runs, which 7.2 forbids. All 19 trigger-to-note pairs are recoverable with their printed pairings.
- **Unit assembly and the furniture drop** (`dawmans/corpus/pdf/units.py`). Stage 7 clears the
  furniture mark inside detected tables, then drops what is still marked, ending the mark-then-clear
  ordering: a numeric line inside Nitro Max's note table survives while the repeated page number does
  not, and text is discarded exactly once. Table rows and numbered procedures are emitted `atomic`
  (6.10, 7.4) and the joined heading `repeat_on_split` (7.5); a procedure broken across a page break
  stays one unit carrying both page numbers; `has_figures` is set only where a placed image covers at
  least 2% of the page (10.3); printed contents pages and non-English blocks contribute nothing.
- **The vendor-manual load path** (`dawmans/corpus/pdf/loader.py`). `PdfLoader` behind the
  `SourceLoader` protocol (12.4), running the stages in the order the design calls load-bearing —
  extract, furniture mark, glyph repair, section map, language selection, unit assembly — and
  deciding the three rejections that need a source to have been read: no text layer (3.3), over the
  unmappable-character threshold (5.5), no English content (4.5). A rejected source still yields a
  `SourceRecord` and an ingestion audit.
- **Text conditioning: furniture, glyph repair and English selection** (`dawmans/corpus/pdf/`,
  `data/manual-corpus` phase 4). Three stages that annotate the span model rather than rewrite it.
  `furniture.py` marks running headers, running footers and standalone page numbers in the top and
  bottom 8% bands (3.6) and deletes nothing — the mark is cleared again by sectioning and by table
  detection, and the drop is the chunker's. `glyphs.py` repairs the APC Key 25's Clip Stop arrows,
  which its `Wingdings3` ToUnicode CMap mangles into `ð, ñ, ô, õ`: detection is font-keyed, so the
  genuine French `ô` printed two lines away in the body face survives, and so do the `Symbol`
  bullets on the same page. What cannot be mapped becomes U+FFFD and sets `degraded` (5.3), and over
  2% of the extracted text layer is the `unreadable-text` rejection (5.5). `language.py` scores
  blocks with `lingua` where the declared language is `multi`, and does not score a source declared
  with one code at all — Live's 3,979-word keyboard-shortcut chapter has 24 full stops in it and no
  identifier calls it English.
- **PDF extraction and the span model** (`dawmans/corpus/pdf/extract.py`, `data/manual-corpus`
  phase 3). `page.get_text("dict")` per page into `Page`/`Block`/`Line`/`Span`, each span keeping its
  bbox, font name, size and flags so glyph repair can key on the font, row assembly on geometry and
  language selection per block. The dict flags clear `TEXT_PRESERVE_IMAGES`: PyMuPDF's default
  materialises every image's bytes into type-1 blocks, which is both 10.1's "image content is not
  extracted" and, against Live 12's 96 MB of screenshots, a seventeen-fold cost on the page measured.
  Images survive as placement rectangles only, which is what 10.3's figure test needs and all it
  needs. Page numbers are physical 1-based indices. `has_text_layer` (3.3) and `low_text` (3.4) are
  derived from the model, the latter over the whole text layer **before** language selection — after
  it, every multilingual guide would be flagged for having translations.
- **The committed extraction fixtures** (`tests/fixtures/`, `tools/capture_fixture.py`,
  `make fixtures`). `manuals/` is gitignored, so no test may open a reference PDF: the nine vendor
  fixtures are snapshots of what the extractor returned for a named page range, which also pins its
  output as an explicit input to every downstream stage. The APC guide is committed redacted — text
  masked to its character classes, one language label per block — because 24 pages of it verbatim
  would be substantially the whole guide, and because the measurements the language stage makes are
  measurements of shape. Three synthetic rejection fixtures cover no-text-layer, over-threshold
  unmappable characters, and the two filename rejections.
- **Source discovery and identity** (`dawmans/corpus/discover.py`, `data/manual-corpus` phase 2).
  The filename grammar of 2.1–2.3 as one anchored expression, with `SourceIdentity.filename` as its
  exact inverse: `api/answer-engine` rebuilds a name from a `SourceRecord`'s own fields to serve the
  PDF behind a citation (CONTRACTS §3a) and to assemble `required_manual` (§4e), so `doc_version` is
  stored without its leading `v` and the round trip is asserted as a property. `source_id` is
  `<vendor>/<product>` with the version deliberately outside it, and the shard slug maps `/`→`_`
  rather than `/`→`-`, which would fold `a/b-c` and `a-b/c` onto one shard.
- **Both source stores scanned in one run, and a missing store distinguished from an empty one.**
  An absent, unreadable or not-a-directory store reports as unavailable and its discovery set is
  *unknown*, so no shard from it is removed; only an existing, empty store removes its shards. That
  is what stops an unmounted volume deleting every authored passage and reporting success. Removal
  is keyed on the store recorded in the shard's own meta, so 9.5's "never test a source of one kind
  against the other kind's store" holds by construction, and a removed source takes its view sidecar
  and its ingestion audit with it.
- **Discovery rejections, per 1.3, 2.5 and 2.6.** A malformed filename is reported with the offending
  name and the expected pattern; two files resolving to one `source_id` reject both rather than
  silently indexing one, and a shard standing under a rejected identity is removed. A non-PDF in
  `manuals/` is skipped with no report line. The run-level pass also catches the one collision no
  single store can see — a vendor manual named `authored_triage_*.pdf` lands on the authored store's
  constant identity, which the slug rule cannot distinguish.
- **The `dawmans` Python package, scaffolded** (`data/manual-corpus` phase 1). `src/` layout managed
  with uv, the module tree of the design's Module placement, and the Makefile targets that were
  still erroring: `build`, `test`, `lint`, `clean`, plus `fetch-model` (the one-off model cache
  population that keeps requirement 8.5's ingestion offline) and `bench` (the 8.1 full-corpus
  timing, which skips when `manuals/` is empty). `index/` and `models/` are gitignored.
- **The AGPL confinement is enforced, not just documented.** PyMuPDF may be imported only under
  `dawmans/corpus/pdf/` (`data/manual-corpus` Decision 6). A ruff banned-api rule catches the import
  form and `tests/test_agpl_confinement.py` walks the package AST, so `make test` catches the
  dynamic form the linter cannot see.
- **`SourceRecord` and `Passage` — CONTRACTS §1 and §2 as code.** Frozen, keyword-only records whose
  field set is asserted against the contract tables. The constructors refuse a field the record's
  kind marks not applicable rather than defaulting one into place (9.1, 12.5), pin an
  `authored-triage` source to the constant `authored/triage` and `assumed` applicability, and keep a
  pageless passage's section and page fields absent while requiring its `entry_location` (12.8).
- **The loader seam** (`dawmans/corpus/loader.py`): `SourceLoader`, `Discovered`, `LoadResult`,
  `Region`, `Unit`, `UnitFlags` and the closed `Rejection` reason set. Interfaces only —
  `TriageLoader` is `data/symptom-triage`'s to write, and everything from `Region` onwards is the
  shared code that makes 12.2 structural.
- **End-to-end, serve wiring and timing** (`api/answer-engine` phase 9, `dawmans/cli.py`,
  `tools/bench.py`). `dawmans serve` is wired on `run_serve` in `cli.py` with the four-step
  startup order of design §What the engine reads: the loopback check first of all — a refusal
  never pays the 7.2 s model load — then the manifest read and view load (raising on a
  present-but-unreadable manifest, serving an empty corpus on a missing one), then the embedding
  model loaded and warmed with one throwaway encode, and the bind last, so no listener accepts
  before the warm. The model loader and server runner are injectable seams; the resident BGE
  tokeniser backs `count_tokens` (Decision 8 — no provider SDK call before `stream()`), the
  provider factory constructs each kind against its own base URL with the keyed constructor as
  the stored key's only reader, and the 6.11 `SecretFilter` is installed on the logging handler.
  All serve-side imports are deferred so the shared CLI stays importable in an ingest-only
  environment. End-to-end tests (`tests/answer/test_end_to_end.py`) drive the full stack minus
  the socket — a real `ViewWatcher` over a synthetic on-disk index written view-directory-first
  and manifest-last, the guarded app, the pipeline, scripted providers — covering one turn per
  content outcome (answered with citations from both kinds, a `!conflict` with both readings
  separately cited, a partial answer naming `uncovered_parts`, a refusal with resolved
  suggestions, out-of-domain with suggestions suppressed, no-manual-for-device resolving
  `required_device` and `required_manual` through a fixture gaps report), the narrowing entry
  path run to its limit and terminating in `ranked-causes`, `contributing_sources[]` on every
  answer, and the mid-conversation corpus swap (a removed source drops with `scope_dropped`;
  removing the last yields `no-sources-selected`). Startup order and wiring tests are
  `tests/answer/test_serve.py`. The CI timing tests (`tests/answer/test_timing.py`) hold 4.2
  (retrieval ≤ 10 ms median / ≤ 50 ms p95) and 4.3 (engine overhead ≤ 150 ms p95, stub provider)
  against a synthetic 1,200-chunk index, with retrieval and state acquisition excluded from the
  overhead cap and each held to its own budget; `make bench` (`tools/bench.py`) covers 4.1 and
  4.6–4.8 against a real provider and a real index, skipping honestly when either is absent,
  measures a narrowing question against the first-token target only (7.3), and calibrates
  Decision 8's 10% history-token margin against the provider's `count_tokens`.

- **The local HTTP surface** (`api/answer-engine` phase 8, `dawmans/answer/http/guard.py` and
  `dawmans/answer/http/app.py`). `guard.py` holds the two 9.1–9.3 guards: `ensure_loopback_bind`
  refuses a non-loopback bind before uvicorn exists — exiting non-zero naming the address and the
  constraint, no fallback bind — and `HostOriginGuard` is the pure-ASGI middleware rejecting any
  request whose `Host` is not the loopback service with the port (the check that closes DNS
  rebinding) or whose `Origin` falls outside the same set, including `null` and the cross-port
  dev-server origin; rejection is 403 with a machine-readable reason and no `outcome`. `app.py`
  carries the design's route table: `GET /passages/{id}` as a dict lookup routed on the source_id
  prefix running the same stat change check as a turn (3.4), `GET /sources` relaying every 9.5
  field for both kinds plus both gap reports verbatim — owned-but-undocumented as an empty list,
  never an omission (9.6–9.7) — and reporting an unreadable new manifest as a fixed notice with no
  filesystem path in any payload; the five provider operations over a new `ProviderRegistry`
  (masked-only throughout per 9.8, shared-backend selection recording nothing until the 6.15
  disclosure is acknowledged, credential changes re-constructing the keyed provider so 6.3 holds,
  test-provider probing reachability without synthesising a turn); serve-document rebuilding
  `<vendor>_<product>_<doctype>_v<doc_version>_<lang>.pdf` from the record's own fields,
  realpath-confined to the manuals root, served inline with Range honoured and no
  Content-Disposition filename so `#page=N` survives (9.4); and `POST /turn` streaming the
  CONTRACTS §4b sixteen-event set over SSE with per-event payload mapping, `done` carrying
  `{"complete": true}` (9.14), the `dawmans/turn-stream/1` version header plus the minted
  conversation id readable before the first body byte (9.15), the 9.12 over-length rejection as a
  422 with no outcome and no turn started, and the `web/build` static mount that makes the surface
  same-origin. A caller disconnect now cancels the turn deterministically (9.10): the response
  finalises its body iterator, the encoder closes the turn generator, `TurnPipeline._run` closes
  its inner event generator, and the provider release cancels an in-flight `anext` before
  `aclose` — previously the provider stream was only released at garbage collection. Tests cover
  the guard matrix, the gap relay, credential masking against captured logs, filename round-trip
  and confinement probes, stream completeness against the pipeline's own event sequence, §4b
  ordering on the wire, and incremental delivery and disconnect at the raw ASGI layer.
- **Conversation and the turn pipeline** (`api/answer-engine` phase 7,
  `dawmans/answer/conversation.py` and `dawmans/answer/turn.py`). `conversation.py` holds one
  conversation's in-memory state: the last 6 content-outcome turns rendered for the prompt's
  context-only history block (10.1), the carried scope with display names captured at set time so
  5.11's turn-time prune can report a source the view no longer names, the per-symptom
  consecutive-narrowing counter that 7.5's terminal direction rides on (incremented by
  needs-narrowing, reset by an answer, untouched by engine failures), and 7.4's follow-up query
  assembly — a turn answering a narrowing question retrieves with the original symptom question
  plus the answer, never the previous turn's passages, and there is structurally nowhere to retain
  a passage. `turn.py` is the pipeline the design pins there: retrieval under `asyncio.to_thread`
  gathered with `StateSource.snapshot` under `wait_for(0.100)` so the state task genuinely runs
  alongside synchronous numpy work (4.4, 8.9), the pre-flight and in-flight gates, engine-side
  narrowing/`causes[]` construction on the entry path with back-filled citations and the per-turn
  `unbacked` reading, prompt assembly carried to providers as the new pre-rendered
  `SynthesisRequest.user` (Decision 11 — the roster and the terminal direction reach every
  provider through the one renderer), the 10 s first-token watchdog naming the provider (4.9),
  supersede-based per-conversation cancellation whose old stream emits `outcome: cancelled` then
  `done` before the new one opens with the provider released by a close, not a drain (4.10, 9.13),
  incremental §4b event emission with unresolvable markers stripped from the streamed text,
  mid-stream failure degrading to `incomplete` with the partial retained (6.10), state faults
  degrading to manual-only with the note logged (8.8 — the closed event set has no field for it),
  supplied-derived `contributing_sources[]` (5.9), and `timings` as durations only for the five
  stages (4.11). `parse.py` gains the streaming seam (`on_body_line` plus read-only header
  properties) so deltas can flow without envelope fields leaking into `body`. Tests cover the
  concurrency shape by wall clock, every degradation path, the watchdog, the cancellation
  property over arbitrary stream prefixes, provider switching without restart, cross-source
  citation with the small guide under the floor, and the scope prune to `no-sources-selected`.
- **Providers, credentials and the state seam** (`api/answer-engine` phase 6,
  `dawmans/answer/provider/` and `dawmans/answer/state/`). `provider/base.py` defines the seam:
  `ProviderKind` with `requires_key` derived from the kind (6.4), the verbatim `SynthesisRequest`
  with `max_words` fixed at 400, the masked-only `ProviderStatus` (no field can hold a full key),
  the four-kind `ProviderFailure`, the `Provider` protocol whose `stream()` yields text deltas and
  nothing else (Decision 4), and the single shared user-prompt renderer that keeps 6.2 structural.
  `provider/anthropic.py` drives `AsyncAnthropic` against `claude-opus-5` with the pinned settings
  table — thinking disabled at effort low, `max_retries=0`, a 30 s / 2 s-connect timeout so the
  engine's watchdog fires first, `cache_control` on the last system block — the single-retry
  rate-limit policy (retry only a stated interval ≤ 3 s, before any output, the value unrounded on
  both branches and absent when unstated), connection/auth/status errors mapped to the failure
  kinds, and `prompt_cache: unavailable` reported for models whose cache minimum the system prompt
  does not clear. `provider/local.py` is an OpenAI-compatible httpx client that refuses any
  non-loopback base URL at construction, so 6.14 holds by construction; `provider/shared.py` is
  the stub behind the 6.15 disclosure gate. `provider/credentials.py` stores keys in the macOS
  Keychain via keyring under service `dawmans`, account `anthropic` (Decision 6), returns only the
  last-4 masked form on every read path but the client constructor, and ships the secret-dropping
  `logging.Filter` whose predicate also scrubs CONTRACTS §4 `detail`. `state/base.py` and
  `state/null.py` land the flat `StateValue` triple (Decision 7), `StateSnapshot`, the
  `StateSource` protocol and the immediate-empty `NullStateSource` (8.3). Tests cover the pinned
  SDK settings, the rate-limit branches, failure-kind mapping, loopback-by-construction with
  networking poisoned, the disclosure gate, the same envelope shape through all three provider
  classes, and credential storage/masking with keyring stubbed (the live Keychain path runs on a
  developer machine only, per `prerequisites.md`). `httpx` is now an explicit member of the
  `serve` extra.
- **Prompt, parser, grounding and the outcome procedure** (`api/answer-engine` phase 5,
  `dawmans/answer/prompt.py`, `parse.py`, `ground.py`, `outcome.py` and the new
  `dawmans/triage/terms.py`). `prompt.py` assembles the turn in cache order — the static system
  prompt as the cache prefix (framing spec, no-uncited-facts rule with the facts-versus-reasoning
  split, length caps, edition caveat, kind trust split, refusal and out-of-domain directions with
  2.9's authored-entry carve-out, the no-XML instruction and no "do not think" anywhere), then
  passages, the metadata-only unselected-source roster, the labelled uncitable state and history
  blocks and the question — with history bounded oldest-first to 800 tokens at a 10% margin by an
  injected local tokeniser (Decision 8, no provider SDK call before `stream()`), and the narrowing
  counter carried into assembly at the limit (7.5). `parse.py` is the incremental line-oriented
  parser for `dawmans/answer-framing/1`: total over bytes, line 1 validated against the
  seven-member content enum with the unparsed fallback restricted to the coverage pair, §4d block
  typing at column 0 with unknown lines degrading to paragraphs, `!conflict` arity reported
  through `framing` without re-typing, and sigil hoists (`~uncovered`, `?narrow`, `?cause` with
  rank from emitted order, `@device`, `!suggest` resolved against sources.json — at most 3,
  absent when none survives). `ground.py` makes 3.6 structural: citations assemble only from the
  supplied set, unknown markers are stripped and counted, the field copy emits absent as absent
  on pageless sources, and the two-arm ungrounded rule (fact-shaped tokens via the reused
  `dawmans.triage.terms` extraction primitives, plus uncited ordered steps) executes the
  CONTRACTS §8 split. `outcome.py` classifies every turn totally and disjointly: four pre-flight
  and six in-flight gates in fixed order (cancelled ahead of incomplete, incomplete ahead of
  every error kind, 401 as `authentication-failed` distinguishable from `missing-credential` by
  sub-code alone), plus the `required_device` resolver over the gaps report and `required_manual`
  assembly with named placeholders — absent where the device does not resolve. 107 tests
  including totality, disjointness, round-trip and non-citability properties.
- **Narrowing from triage entries** (`api/answer-engine` phase 4, `dawmans/answer/narrow.py`).
  The engine-built entry path of Decision 9: `matched_entry` finds the first supplied passage
  keying the triage sidecar, `expand_entry` takes the entry's first ≤ 4 causes in the author's
  order and resolves each cause's fix pointers against the view — filtered through the turn's
  source scope (Decision 10), bounded over resolved passages rather than pointers at the
  12-passage cap, with excess dropped in cause order and within a cause in section order, and
  passages retrieval already supplied cited without re-admission. `build_narrowing` constructs
  the 7.2 candidate list (label from `check`, value from `statement`, no reorder/merge/add) with
  7.8's state-value suppression behind a caller-supplied predicate, asking nothing when fewer
  than two candidates survive; `build_causes` builds the 7.6 terminal `causes[]` with positional
  ranks, the entry passage as `cites[]`, and scope-filtered `fix_cites[]` — empty `fix_cites[]`
  reads as unbacked for the turn (the engine reads the authored flag, never sets it), and
  out-of-scope holding sources are named for 2.3's suggestion path. 20 tests cover the
  provenance, scope, bound, suppression and terminal-form properties.
- **Retrieval and scoping** (`api/answer-engine` phase 3, `dawmans/answer/scope.py` and
  `dawmans/answer/retrieve.py`). `device_scope` derives the turn's device scope over source kind —
  the selected vendor manuals' `hardware_applicability.device` unioned with the
  owned-but-undocumented gaps, widening to every indexed vendor-manual device when no vendor
  manual is selected — and `in_device_scope` is 5.13's predicate: a passage declaring devices
  disjoint from the scope is excluded from the turn entirely, a filter and never a ranking input.
  `candidate_pool` runs the design's retrieval order — BGE query-prefix embed, candidate mask
  (selected row slices minus device-filtered rows), masked dense and lexical rankings, RRF fusion
  at k=10 — with masking *preceding* top-k on both retrievers so out-of-scope rows never consume
  the depth-50 slots. `retrieve` applies the two-arm relevance threshold (cosine ≥ 0.30, or BM25
  rank 1 *within its own source* sharing a query term of document frequency ≤ 5%) with both
  constants as configuration, per-source qualification, and Decision 5's allocation: one floor
  slot per qualifying source, remaining slots by fused rank, cap `max(8, |qualifying|, 12 on a
  narrowing expansion)`. No qualifying in-scope candidate means the turn is uncovered per 2.1.
  38 tests cover the scope derivation, the mask-precedes-top-k behaviour, the fusion
  monotonicity/invariance/decisiveness properties Decision 1 rests on, the threshold arms and the
  floor/cap precedence property.
- **The corpus view** (`api/answer-engine` phase 2, `dawmans/answer/view.py`). `CorpusView` loads
  one immutable revision of the merged index view in the design's load order — manifest first,
  refusing to serve on an `index_version` the engine cannot interpret — then mmaps `vectors.npy`
  and reads `passages.jsonl`, `lexical/`, `sources.json`, `gaps.json` and the triage sidecar.
  Source scoping is a row slice from `manifest.sources`, not a scan. The sidecar filename is
  derived by the slug rule from the `authored/triage` constant, never spelled; a view whose
  sidecar is missing (e.g. hyphenated) fails loudly rather than serving with no device
  declarations. `ViewWatcher` stats the manifest before each turn: a `corpus_revision` change
  discards the view wholesale so no answer can mix revisions, an in-flight turn keeps the view
  object it holds, an unreadable new manifest keeps the live view and records the fault for
  `GET /sources` (never `corpus-empty`), and the reload cost lands on the run-level
  `corpus_reload_ms`, never on a turn. 21 tests cover load, refusal, slices, the sidecar rule and
  the revision watch.
- **The `dawmans` Python package** (`api/answer-engine` phase 1). `src/` layout on uv + hatchling,
  with the `dawmans.answer` module tree from the design's module placement, a `dawmans` CLI whose
  only registered subcommand is the `serve` stub, and `make build`/`test`/`lint` wired to uv,
  pytest and ruff.
- **The ingest/serve dependency split.** `[project.optional-dependencies]` confines PyMuPDF (AGPL),
  lingua and fonttools to `ingest`; the API host syncs `serve` (fastembed, bm25s, numpy, anthropic,
  starlette, uvicorn, keyring) and never installs PyMuPDF. A subprocess test imports every
  `dawmans.answer.*` module with `fitz`/`pymupdf` poisoned on `sys.meta_path`, catching the
  accidental corpus import a dual-group dev environment hides.
- **The envelope records and outcome enums** (`dawmans/answer/envelope.py`). Frozen dataclasses
  `Citation`, `AnswerEnvelope`, `Cause` and `RequiredManual` whose field sets are exactly the
  CONTRACTS §3/§4/§4c/§4e tables, and `Outcome` (17 members) / `Reason` (5 values) StrEnums closed
  to CONTRACTS §6/§6a. Construction enforces the contract invariants: absent is `None` and never an
  empty string, an authored-triage citation cannot carry a page, section number or `doc_version`,
  `entry_location` is authored-only, a cause's `rank` equals its position in `causes[]`, and
  `retry_after` is non-negative and unrounded. 32 tests assert the field sets and invariants.
- **`web/src/routes/+page.svelte` — the assembled surface** (`ui/ask-and-source-picker` Phase 9).
  One page: scope bar, thread and ask input, with the picker, history, provider configuration and
  expanded passages as regions, not routes, so no transition can discard the typed question or
  the scope (10.2, 10.11). The page wires what no component owns: the loads on mount (sources →
  scope, provider), a submission gate blocking the turn while the source list is not ready (9.13)
  or the shared-backend disclosure is unacknowledged (10.4), the 3.6 release notice with its
  one-activation reinstate, the engine-unreachable and corpus-empty states, and the provider
  region's place on the Escape stack. The layout applies the design tokens to the body and keeps
  the thread at ≥ 70% of the viewport at rest (11.8).
- **`web/src/routes/page.test.ts` and `web/src/lib/testing/fake-server.ts` — the integration
  suite** (Phase 9). A fake engine server over global fetch, so full turns exercise the real
  client → SSE → reducer → renderer path for every renderer family and error outcome with no
  provider, corpus or key; the keyboard-only core loop asserted at component level (1.13); region
  transitions asserted to preserve question and scope (10.2, 10.11); and CONTRACTS §4b re-checked
  at the integrated level — one visible discharge per governed event, typed as a total record so
  a seventeenth event fails the type check.
- **`web/e2e/` — the Playwright browser and accessibility suite** (Phase 9). A scripted stub
  engine behind the real vite dev proxy proves in a live browser: no already-painted line moves
  while streaming (4.2); the core loop with zero pointer use (1.13, 13.1); open-at-source at
  exactly `#page=N` in a new tab and the authored entry revealed in place (5.5, 5.19); Escape
  returning focus to each region's opener (13.3); a mid-stream citation expand/collapse leaving
  the entry at the same viewport offset (5.8); one announcement per state transition and never a
  fragment (13.5); the ≥ 70% chrome ratio (11.8); every 11.6 distinction surviving greyscale; no
  horizontal scrolling at the 200% text-size equivalence (13.7); the reduced-motion counter with
  distinct static state shapes (13.6); and an axe-core WCAG A/AA floor over every rendered state
  (13.2, 13.4, 13.8). Run with `make web-e2e`.

### Fixed

- **`CitationEntry` reading-position restore scrolls the real scroll container** (5.8). The
  collapse restore called `window.scrollBy`, a silent no-op on the assembled page where the
  thread scrolls inside a container; it now scrolls the nearest scrollable ancestor, falling back
  to the window.

### Added

- **`web/src/lib/components/SourcePicker.svelte` — the source picker** (`ui/ask-and-source-picker`
  Phase 8). Collapsed at rest to the one-line scope indicator, which is itself the expand/collapse
  control (2.11): "All N sources in scope" (2.7), names at three or fewer in scope (2.6, 3.3), else
  "n of m", with a scope glyph as the greyscale-safe channel (3.10, 11.6). Expanded: per-source
  checkboxes with a filled/hollow marker plus the word in/out of scope (2.14), the kind stated on
  every entry so authored notes are never mistaken for vendor documentation (2.12), the
  assumed-revision and sparse-text marks (2.10), all/none controls (2.8), a substring filter from
  twelve sources (2.13), and the known-gaps group rendered apart, never selectable, and omitted
  entirely while the report is empty (2.9). Registers on the router's Escape stack while expanded
  (13.3).
- **`web/src/lib/state/provider.svelte.ts` and `ProviderConfig.svelte` — provider configuration**
  (Phase 8). Kind-first configuration over the five provider operations (10.1): a local provider
  configured from its endpoint or model alone and never asked for a key (10.3); the key input
  masked with a hold-to-reveal, always empty on open, cleared after save so the engine's masked
  tail is the only representation anywhere (10.5, 10.6); replace, clear and test-provider (10.8,
  10.10); status rendered only from `GET /provider` (10.7). The shared-backend disclosure blocks
  the first turn until explicitly acknowledged, stays readable afterwards, and is stored against
  the engine-reported backend identity so changing backend re-arms it (10.4).
- **`web/src/lib/components/HistoryPanel.svelte` and thread retention** (Phase 8). Retained
  exchanges newest first with question and time (12.2); selecting one re-displays the stored
  answer, scope-at-ask and citation records with no fetch (12.3, 12.4); re-ask starts a new
  conversation against the current scope (12.5); clear-all behind a confirmation step (12.6);
  mounted only while open, one activation each way, dismissed by Escape to its opener (12.8,
  13.3). `history.svelte.ts` now records the client-minted conversation id on each entry so a
  narrowing exchange is retained as part of its thread, never as a standalone unanswered
  question (6.7).

- **`web/src/lib/state/perf.svelte.ts` — per-turn marks and the slow-wait thresholds**
  (`ui/ask-and-source-picker` Phase 7). `submit` is stamped at Turn construction in the submit
  handler, `firstByte` when the first content event leaves the SSE reader, and `firstPaint` in a
  requestAnimationFrame after that content is in the DOM; `measures()` computes 8.8
  (firstPaint − submit) and 8.9 (firstPaint − firstByte), returning nothing where a mark is
  absent. `SLOW_THRESHOLD_MS` fixes the "taking longer than usual" threshold per provider class —
  hosted 3 s, local 5 s, inside 8.10's bands.
- **`web/src/lib/components/WorkingIndicator.svelte` — the waiting states** (Phase 7). Shown
  below the thread while the active turn awaits first content, so its removal cannot shift
  painted text (8.2, Decision 2); the submitted question stays visible while waiting (8.3).
  Unmistakably live by animation — the surface's only animation beside arriving text (11.9) — or,
  under `prefers-reduced-motion`, an elapsed-seconds counter paired with the static shape,
  excluded from the announcement region so ticks are never announced (13.6, Decision 7). Past the
  per-provider-class threshold, plain "taking longer than usual" text and a cancel control appear
  (8.5); cancelling returns to ready with the question preserved and partial output never
  presented as finished (8.6).
- **`web/src/lib/components/ErrorView.svelte` — the §9 error renderers** (Phase 7). Every error
  outcome states what happened plainly with at least one action and never raw exception text
  (9.1, 9.2): `provider-unconfigured` keyed on the `reason` sub-code alone, opening provider
  configuration with the typed question preserved (9.5); `provider-unreachable` naming the
  provider (9.6); `timeout` attributing the stall to the provider, distinct from unreachable
  (9.7); `provider-rate-limited` counting `retry_after` down where supplied and stating honestly
  where the provider gave no interval (9.8); `provider-error` retrying with `detail` behind the
  disclosure (9.9), or offering configuration in place of retry on `authentication-failed`
  (9.10); `unknown-source-id` naming the rejected ids, dropping them from the stored scope and
  re-asking the remainder in one activation (9.11); `no-sources-selected` as the 3.2 empty-scope
  state (9.12); `corpus-empty` naming `manuals/` and the ingestion step (9.13). Broken states
  carrying no outcome render here too: a malformed-request rejection naming what was rejected
  (9.15), an unknown turn-stream version naming both versions (9.19), and an unrecognised
  outcome (9.4).
- **`web/src/lib/components/DiagnosticsDisclosure.svelte` — the 9.3 disclosure** (Phase 7).
  Renders exactly the engine's `detail`, `framing` and `timings` plus the client's per-turn
  marks — nothing else, nothing parsed out of `detail`, no request echoed (which keeps 9.17
  structural). Mounted on every failed/error/broken turn and on any turn carrying
  `framing: unparsed`.

### Changed

- **`web/src/lib/components/ThreadView.svelte`** (Phase 7): per-turn state now signals through
  two channels — a static glyph beside the text label, never colour alone (8.4); the error
  family (including failed turns with no outcome) routes to `ErrorView`, `cancelled` retains
  whatever arrived, `incomplete` turns keep their partial text marked with a retry (9.14), and an
  engine-cancelled turn the user did not cancel is marked abandoned without disturbing its
  replacement (9.16). One `aria-live="polite"` region announces streaming started, finished,
  failed, coverage failure, partial answer and narrowing — with its candidates and that digits
  select them — once each (13.5).
- **`web/src/lib/components/AnswerView.svelte`** (Phase 7): the streamed body is
  `aria-live="off"` with `aria-busy` while streaming, so fragments are never announced
  individually (13.5); the first painted content schedules the `firstPaint` mark.
- **`web/src/lib/engine/turn.svelte.ts`** (Phase 7): `Turn.marks` is reactive and the
  `direct_answer`/`body_delta` handlers stamp `firstByte` on first content.

### Added

- **`web/src/lib/components/NarrowingView.svelte` — the narrowing renderer**
  (`ui/ask-and-source-picker` Phase 6). `needs-narrowing` renders the question and its 2–4
  candidates visually distinct from an answer, a coverage failure and an error (6.1), each a
  separately activatable control numbered in the engine's order — never reordered, merged or
  added to (6.2). The digits arm through the keyboard router's registry while the list is the
  thread's last settled turn, with the armed keys indicated on screen (6.3, 1.11); selection
  submits a follow-up turn in the current thread against the unchanged scope, keeping the
  question and the chosen candidate visible (6.4); typing any other printable begins a free-text
  reply through the router's capture without dismissing the list (6.5); the question paints from
  its first event, never held back until the turn settles (6.8).
- **`web/src/lib/components/RankedCausesView.svelte` — the ranked-causes renderer** (Phase 6).
  `causes[]` renders in array order with each `rank` shown, as findings to read — never the
  digit-armed controls of a narrowing question, the affordance split that keeps the two
  candidate-bearing shapes apart (6.6). The rank-1 cause's `check` arrives as `direct_answer` and
  paints first, so the first cause is never promoted to an answer; `cites[]` and `fix_cites[]`
  resolve through the turn's one citation map by `passage_id` via the new shared
  `citation-order.ts` numbering (also adopted by `CitationList`), and a cause with an empty
  `fix_cites[]` carries the `unbacked` mark rather than simply appearing without a fix (5.16).
- **`web/src/lib/components/CoverageFailureView.svelte` — the coverage-failure renderer**
  (Phase 6). One renderer for `refused-not-covered`, `out-of-domain` and `no-manual-for-device`
  with the per-outcome action table: plain not-covered wording with no synthesised answer (7.1)
  naming the sources in scope at ask time (7.3); add-the-suggested-sources-and-re-ask in one
  activation from addressable values (7.4); widen-all-and-re-ask where nothing is suggested and
  out-of-scope sources exist, suppressed on the two outcomes the engine has already judged
  uncoverable (7.5); technique wording with the question re-editable on `out-of-domain` (7.6);
  the `required_device` with the copyable `required_manual` filename and its `placeholders[]`
  named from the field — never split out of the filename, and the `manuals/` naming convention
  stated where the dormant field is absent (7.7). Under a narrowing the gap is attributed to the
  narrowing in force (3.10); a widen persists and decays like any scope change (7.9); with all
  sources already in scope the state says so and falls through to the filename action or
  re-editing, never dead-ending (7.8, 9.2).
- **History entries carry their thread** (Phase 6). `HistoryStore.record` now stores the
  client-minted conversation id as `entry.thread`, so a narrowing exchange is retained as part of
  the thread it belongs to and never as a standalone unanswered question (6.7).

### Changed

- `ThreadView` routes the `narrowing`, `ranked-causes` and `coverage-failure` renderer families
  to the new Phase 6 components, passing the keyboard router and a source-name resolver down;
  only the Phase 7 error families keep the plain-text placeholder.

### Added

- **`web/src/lib/components/AnswerView.svelte` — the answer renderer** (`ui/ask-and-source-picker`
  Phase 5). The §4 renderer over the reducer's blocks and envelope, presentation only:
  `direct_answer` first (4.3), every CONTRACTS §4d block and inline type visually distinct —
  headings, separately identifiable steps (4.5), bullets, paragraphs, `!caveat` in reading
  position and never behind a disclosure, `!conflict` with both readings and their separate
  citation markers, neither chosen (4.4) — backtick key terms as discrete `<kbd>` elements never
  smaller than body text (4.12), and markers as their stable first-appearance integers
  (Decision 3). A turn carrying `scope_dropped[]` names the dropped sources with that turn as the
  engine's prune, never the user's own narrowing (3.11); `contributing_sources` are named
  distinctly from the merely-in-scope (4.7); `partially-answered` renders as an answer with each
  uncovered part visually subordinate and a per-part control that re-asks it alone, widening scope
  to the engine-named sources with the answered part left on screen (4.8, 4.9). ThreadView routes
  the `answer` renderer family here.
- **`web/src/lib/components/CitationList.svelte` / `CitationEntry.svelte` — the citation list**
  (Phase 5). One entry per marker integer in first-appearance order, each carrying every
  CONTRACTS §3 obligation inline with no disclosure in the path (Decision 3): `doc_version`
  (5.2), assumed `hardware_applicability` naming the revision described (5.3), "figure on pN"
  (5.4), the authored kind as the user's own note distinguishable in greyscale (5.14), and
  `unbacked` (5.16). The location slot renders `section_number` and `section_title` as the two
  fields they are with only what exists (5.1); a pageless authored citation shows its symptom
  title with page and section absent (5.15); `entry_location` sits beside the open action,
  copyable in one activation, never in the location slot (5.19). A settled answer with no
  citations is marked uncited (5.12) and `ungrounded` marks the rendered text as unverified
  without blanking it (5.13).
- **`web/src/lib/state/passages.svelte.ts` — the session passage cache** (Phase 5). A `Map` of
  loading/ready/failed states over the fetch-passage operation, prefetched on focus and never on
  hover (1.12, 5.18): focus precedes activation by a keystroke, so expansion is a cache hit in the
  ordinary case, and a failed entry retries on the next activation. Components fetch nothing
  themselves.
- **Passage expansion and open-at-source on the citation entry** (Phase 5). Expansion reveals the
  passage verbatim in place, visually distinguishable from summary text (5.6, 5.7), with a
  working indicator only past 300 ms on a cache miss (5.18); collapse restores the entry's own
  viewport offset via its rect, not `scrollY` (5.8); `degraded` is marked distinctly from the
  unavailable state, which keeps the source, its cited location and the open action (5.10, 5.11).
  openAtSource is two branches and no third (5.5, CONTRACTS §3a): a vendor manual is a plain link
  — `target="_blank"`, `rel="noopener"`, the serve-document route at exactly `#page=N` — and an
  authored entry is the expansion plus its copyable `entry_location`; no `file://` URL is ever
  attempted.

- **`web/src/lib/keys.ts` — the keyboard router and arming registry** (`ui/ask-and-source-picker`
  Phase 4, Decision 5). One `keydown` listener on `window` with the design's decision table:
  modifiers and foreign text-entry targets pass through; `Escape` dismisses the topmost overlay
  region, returning focus to its opener (13.3); digits 1–4 activate an armed entry (1.11); any
  other printable focuses the question input and inserts the character manually — `preventDefault`
  then append, because the keydown already happened elsewhere (1.2). The registry enforces at most
  one armed set by throwing on a second registration, and window focus restores the input unless a
  region holds it (1.1). One recorded deviation: an armed digit fires even when the target is the
  question input, since focus rests there and arming exists only while it is empty — a literal
  pass-through would defeat 1.10/6.3's one-keypress rule.
- **`web/src/lib/state/thread.svelte.ts` — the thread store** (Phase 4). The conversation on
  screen: the composed draft, the turns oldest first, and submission through the scope store's
  block and the turn state machine — whitespace submits contact no engine (1.5), zero scope blocks
  (3.1), the 1000-character limit is enforced client-side (9.15), and the turn is acknowledged
  synchronously before any fetch (8.7). A user stop retains what arrived and ends the turn as
  cancelled, distinct from an engine abandonment (1.9, 8.6, 9.16); a mid-stream transport failure
  is `incomplete` (9.14); request rejections are kept for the broken-state renderer with no
  outcome synthesised. Conversation ids are minted client-side after the first turn of a thread
  (decision log Decision 8); nothing listens to window focus, so leaving costs nothing (1.12).
- **`web/src/lib/components/AskSurface.svelte` — the ask input and symptom shortcuts** (Phase 4).
  Focus lands in the input on load and window focus (1.1); unmodified Enter submits and
  Shift+Enter breaks the line (1.3); the four symptom shortcuts — no sound, distorting, latency,
  wrong drum sound — render on an empty idle input with their armed digits printed, each
  submitting in one keypress via the registry and equally by pointer (1.10, 1.11). A follow-up is
  indicated with a single new-question control that starts a context-free thread (1.7, 1.8); a
  stop control restores the question for re-editing (1.9, 8.6); the zero-scope state offers
  select-all preserving the typed text (3.2) and the over-limit notice states limit and length
  while the question stays editable (9.15).
- **`web/src/lib/components/ThreadView.svelte` — the thread shell** (Phase 4). Turns oldest
  first, each question inspectable and re-editable in one activation (1.4), with a textual
  working/stopped/abandoned/incomplete/broken/finished state line and a plain-text body
  placeholder until the Phase 5 answer renderer.
- **`web/src/lib/testing/turn-channel.ts`** — the stubbed engine shared by the thread and
  component tests: controllable SSE channels carrying the turn-stream version header, wired to
  the abort signal the way a real fetch is.
- **`ui/ask-and-source-picker` decision log Decision 8** — the thread mints its conversation id
  client-side; the engine issues none and `null` remains the specced way to start a conversation.

- **`web/src/lib/state/sources.svelte.ts` — the sources store** (`ui/ask-and-source-picker`
  Phase 3). Available sources of both kinds plus both gap reports from `GET /sources` — no fixed
  source count anywhere, an added or removed source reflected on the next load (2.1, 2.3). Carries
  the owned-but-undocumented report (empty is the live case; the populated path is exercised
  against a fixture, per CONTRACTS §5), the documented-but-unconfirmed report, assumed
  `hardware_applicability` with the revision it describes, and `low_text` (2.9, 2.10). A failed
  `GET /sources` is an `engine-unreachable` state that blocks submission, distinct from
  `corpus-empty` — the engine answering that nothing is ingested (9.13) — and never renders as an
  empty picker.
- **`web/src/lib/state/history.svelte.ts` — the history store** (Phase 3). Persisted exchanges in
  `localStorage`, read lazily on first access so nothing parses on boot inside 8.7's
  acknowledgement budget (12.1). An entry stores the question, the envelope, the citation records,
  the scope at ask time and a timestamp — never passage text; trimmed to the most recent 50 on
  settle, with a `QuotaExceededError` dropping oldest entries until the write succeeds rather than
  failing the turn (12.9). Cancelled and failed exchanges are not retained as answers; a partial
  kept under 9.14 is marked incomplete (12.7).
- **`web/src/lib/engine/client.ts` — the engine client** (`ui/ask-and-source-picker` Phase 2). The
  nine `api/answer-engine` operations as stateless typed wrappers over relative routes — no host,
  no port, no retries. Non-envelope HTTP failures (422 question-too-long, 403 host/origin) throw a
  typed `EngineRejection` carrying the engine's machine-readable `rejected` name, distinct from any
  outcome (9.15). `serveDocumentHref` builds the open-at-source link as the serve-document route
  plus `#page=N` and nothing else (5.5).
- **`web/src/lib/engine/sse.ts` — the SSE turn-stream reader.** Incremental UTF-8 decoding
  (`TextDecoder` with `{stream: true}`) so a multi-byte character split across network chunks never
  paints as U+FFFD; frames reassembled across arbitrary chunk boundaries; a data-less event never
  dispatched. `turnEvents` checks the `dawmans-turn-stream` version header before reading a single
  body byte, refusing an unknown version by naming both (9.19), and reports end-of-stream without
  `done` as an explicit incomplete signal — never a settled turn (9.14). No reconnection and no
  resumption exist.
- **`web/src/lib/engine/blocks.ts` — the append-only block parser** over CONTRACTS §4d's closed
  set (Decision 2). A block's type is fixed by its first line within at most 10 characters and
  never revised across any chunk split; an unknown first line degrades to a paragraph and never
  emits nothing (4.4); a `!conflict` with other than two readings stays the conflict it declared
  itself. Citation markers `[[p:<passage_id>]]` are buffered from `[` until complete or disproved
  and painted immediately as their first-appearance integer, so late citation resolution cannot
  reflow the line (Decision 3); backtick spans become discrete key-term elements.
- **`web/src/lib/engine/turn.svelte.ts` — the event → Turn reducer.** Fills
  `Partial<AnswerEnvelope>` append-only from CONTRACTS §4b's sixteen events, with the citation map
  keyed by `passage_id` and the marker order list. Two compile-time totality guards: every §6
  outcome maps to a renderer (`Record<Outcome, TurnRenderer>`) and every §4b event has exactly one
  handler (a mapped type over `TurnEvent`); an unknown outcome renders broken carrying `detail`
  (9.4) while an unknown event is ignored (9.19) — deliberately opposite rules. End of stream
  without `done` marks the turn incomplete, retaining the partial text.
- **`web/src/lib/state/scope.svelte.ts` — the scope store** (Phase 3, carried with this change):
  selection, persistence and decay per §3, with `sessionStorage` presence as the session boundary
  and the 8-hour clause on `lastQuestionAt` (Decision 4), silent load-time pruning of stale ids
  (3.8), release-with-reinstate (3.6) and the 2.4 admission rule for newly reported sources.

### Fixed

- **The turn reducer now clones the still-open block on snapshot**
  (`web/src/lib/engine/turn.svelte.ts`, Phase 5). The parser streams into its last block by
  mutating it in place, and under `$state.raw` a keyed render compares items referentially — so a
  delta extending an already-painted paragraph never repainted. The snapshot now
  `structuredClone`s the last block (the only one still open); every earlier block is closed and
  keeps its reference (4.1).
- **`web/vite.config.ts`** — vitest now resolves Svelte's browser entry
  (`resolve.conditions: ['browser']` under `VITEST`), without which component tests fail with
  `lifecycle_function_unavailable`.
- **Web Storage in vitest under Node ≥ 22.** Node's experimental `localStorage`/`sessionStorage`
  globals (lazy getters, undefined without `--localstorage-file`) shadow jsdom's in vitest, which
  skips keys the Node global already owns — so storage was undefined in every test. A
  `vitest-setup.ts` installs an in-memory `Storage` over both globals.

- **`web/` — the browser surface scaffold** (`ui/ask-and-source-picker` Phase 1). A SvelteKit SPA
  built to static assets with `adapter-static` (`ssr = false`, `prerender = true`), for the engine
  to mount at `/` so the page shares its origin (Decision 1). The Vite dev proxy forwards `/turn`,
  `/passages`, `/sources` and `/provider` to `$ENGINE_ORIGIN` and rewrites `Origin` as well as
  `Host` in a `proxyReq` hook, since the engine's rebinding guard rejects a forwarded
  `localhost:5173` origin. Test tooling installed: vitest, @testing-library/svelte, Playwright,
  axe-core. Makefile gains `web-install` / `web-build` / `web-test` and a `make dev` pairing.
- **`web/src/lib/engine/records.ts` — CONTRACTS §1–§4e, §6 and §6a as types**, the only place this
  surface writes them down: `SourceRecord`, `Passage` and `Citation` (the source-kind variants as
  discriminated unions), `AnswerEnvelope`, `Cause`, `required_manual`, the 16-event turn stream,
  the §4d block set, `outcome` as the union of §6's 17 members and `reason` as §6a's five. Absent
  is absent — never empty string, zero or empty array.
- **Design tokens and their enforced floors** (Decision 6). One CSS file of custom properties —
  background, surface, body/secondary text, accent with its 13.8 interactive-state variants, focus
  ring, the four state colours, and the 11.1 type scale — with a unit test computing WCAG contrast
  and luminance from the declared values: body ≥ 7:1, every other text element ≥ 4.5:1, non-text
  indicators and focus ring ≥ 3:1, background luminance ≤ 0.08, and the 11.3-versus-11.5
  resolution held as two enforced bounds (background ≥ 0.03, body text short of maximal white).

- **`data/manual-corpus` task ledger and prerequisites.** 45 tasks over 8 phases, test-then-implement
  throughout, two work streams. `prerequisites.md` records the three things no task can do for
  itself: place the four gitignored PDFs, run `make fetch-model` once, and declare the Focusrite
  applicability mapping.
- **`data/manual-corpus` 11.7 — indexed-but-not-owned.** The ingestion run report names every
  vendor-manual source whose resolved applicability device is not in the rig inventory. Not an
  error: holding a manual for gear you do not own is legitimate. It exists because it is the only
  signal separating that from an **undeclared generation marker**, which puts the device on
  owned-but-undocumented and the source on this line at the same time. That pairing is the
  diagnosis. Recorded as `data/manual-corpus` Decision 9.

### Changed

- **Keyed-line continuation now splits by value kind** (`data/symptom-triage` Decision 7). `check:`
  and `why:` are free text and continue until a blank line, a heading or another keyed line;
  `fix:`, `undocumented:` and `also:` are complete on their own line. Under the single rule the
  grammar previously carried, an ordinary note written under a fix pointer was folded into the
  pointer, which then addressed nothing and rejected the cause with a message naming a line the
  author had written correctly. Found by the cause-conservation property, not by an example.
- **Cause conservation is stated over the total H2 count**, not over the H2s that were not the
  author's closing statement. Decision 6 turns on the parser being unable to tell a genuine closing
  statement from a demoted cause, which is why it flags every inferred one — so the identity that
  actually holds, and the one that makes 1.5 auditable, is causes plus flags equals sections.
  Corrected in the design's Testing Strategy and in the task ledger.
- **`Region` carries `entry_location`** (`data/manual-corpus` Decision 14, design §The loader
  protocol). CONTRACTS §2 requires the field on every authored passage and `records.py` refuses to
  construct one without it, but the seam had nowhere for it to travel. The sidecar cannot supply it:
  it is keyed by `passage_id`, which the chunker is the stage that mints. A region is exactly one
  authored entry, so the field is region-scoped; `TriageLoader` sets it and the chunker copies it,
  never deriving, clearing or hashing it (12.6). `data/symptom-triage` §Passage emission still has
  to name it in its own `Region` construction table.
- **A repeat replaces overlap rather than joining it** (`data/manual-corpus` Decision 15, design
  §Chunking). `data/symptom-triage` needs overlap suppressed for its regions, because a split entry
  would otherwise carry its symptom statement twice in hashed, user-visible text. Stated as "overlap
  is taken only where the continuation copies no `repeat_on_split` unit", the rule reaches that case
  without the chunker knowing what kind of source it has (12.2), and it keeps a split table's full
  room for rows.
- **Stage 7 and the load path are their own modules** (`data/manual-corpus` Decision 13, design
  §Module placement). The design's module tree stopped at `pdf/layout.py`, leaving `Region[]`
  assembly and the loader that sequences the stages without a home. `pdf/units.py` and
  `pdf/loader.py` are added to the tree: `layout.py` keeps to geometry, so a table-detection
  regression is not read against a page-break join in the same file, and `corpus/loader.py` stays
  interfaces only — putting a PyMuPDF-importing class in the module `data/symptom-triage` imports
  would breach the Decision 6 confinement outright.
- **The language-neutral guard is confidence alone** (`data/manual-corpus` Decision 12, design
  §English selection). The design wrote it as low confidence *and* predominantly non-alphabetic
  tokens; run against the real APC guide, that conjunction selected its French and Italian pages as
  partly English. `• Mac OS X : Live > Preferences` scores English at 0.42 with alphabetic tokens,
  so it was trusted, and the short French step below it inherited from it — requirement 4.1 failing
  on the corpus's only multilingual source. Confidence alone covers strictly more than the pair did,
  so the MIDI note table and the specifications table the guard was written for are unaffected.
- **The spelling check skips `tests/fixtures/`.** The fixtures quote vendor manuals verbatim, and
  correcting a manual's spelling would make the fixture a document nobody shipped.
- **The design's account of the corpus, corrected against the corpus** (`data/manual-corpus`
  design §Section map and §Build budget, Decisions 10 and 11). Capturing the fixtures read the PDFs
  rather than describing them, and three claims did not survive: every manual carries an embedded
  outline, so paths B and C of the section map have no live instance and the APC Key 25 is not the
  outline-less document the design took it for; Live's printed contents pages carry no dot leaders,
  so path B's grammar does not detect them; and extraction of the full corpus measures 3.99 s
  against 8.2's 5 s budget, not the ~1 s the estimate extrapolated from a layout extraction. Neither
  path is dropped — they are what the next manual needs — and their fixtures are captured with the
  outline withheld.
- **The last corpus gap is closed, and four mechanisms went dormant with it** (DECISIONS Decision
  12). The Focusrite Scarlett Solo 4th Gen guide is ingested, so every device in the rig is
  documented and the owned-but-undocumented report is empty. Nine files still said otherwise:
  - `data/manual-corpus` 11.4, `api/answer-engine` 2.10 / 5.12 / 9.6, `data/symptom-triage`
    2.3–2.4 and `CONTRACTS.md` §2 / §5 each named the Scarlett as the standing undocumented case.
    All four mechanisms stay implemented and are now exercised against a **fixture rig** declaring
    a device with no indexed source; an empty report is emitted as an empty member, never omitted.
  - `required_manual` (§4e) is the sharpest case: its canonical id resolves *only* through that
    report, so the field Decision 11 added to close defect 6 has never been emitted. Governed,
    implemented, unverified against a real payload — and reachable again the moment a device is
    declared ahead of its manual.
  - `symptom-triage`'s worked example illustrated an unbacked cause with "check DIRECT MONITOR",
    a control the newly ingested guide documents. That cause moves from the unbacked side of the
    rule to the backed side, and the payload example, scope table and fixture list move with it.
- **DECISIONS Decision 2 resolved against itself.** It said `product` "carries the generation where
  that distinguishes the hardware" and then gave `apc-key-25` — whose mk1 and mk2 differ exactly
  there — as an example. The rule now follows the *vendor*: the marker appears where the vendor
  sells it as part of the name (`scarlett-solo-4g`) and not otherwise (`apc-key-25`). Putting the
  generation in the id instead was rejected because it breaks Decision 9: an mk1 guide and an mk2
  device would hold different ids, never meet, and documented-but-unconfirmed could not fire on the
  mismatch it exists to catch.
- The consequence is that `<vendor>/<product>` is **not reliably the rig's device id**. The gap
  reports already joined on a declared `source_applicability.device` rather than on the id, so this
  works — but the 11.2 default does not, and an undeclared Focusrite resolves to a device no rig
  entry holds. Declaring the mapping is now mandatory, and 11.7 catches the omission.
- `manuals/README.md`: the "adding a manual" walkthrough said version 3 where the table says v4.0,
  and omitted the `rig.yaml` step that a generation-marked filename requires.
- `prerequisites.md` listed three PDFs and the Alesis at v1.0 where the tracked record says v1.1.
- **`specs/CONTRACTS.md` amended to close all six open cross-spec defects** (DECISIONS
  Decision 11). Each had been found from both ends of its seam. New governing sections:
  - §3a **Open at source** — the action is mediated by the engine, never by the browser's
    own filesystem access, because a tab served over `http://` cannot navigate to `file://`
    in any current engine and the refusal is silent, making such a control dead rather than
    unavailable. A vendor manual is served same-origin and opened at `#page=N` and nothing
    else; an authored entry is revealed in place through the existing fetch-passage
    operation, with `entry_location` copyable. The engine resolves every target from
    `source_id` — no caller supplies a path, and the index is the allowlist.
  - §4b **the turn stream** — sixteen named events with ordering, a version token, and both
    halves of the unknown-member rule, so a streamed seam is governed like a record.
  - §4c `Cause`, §4d `body` block types, §4e `required_manual`, §6a **reason vocabulary**.
  - §6 gains `ranked-causes` (17 members) with an explicit rule: the taxonomy may be amended
    but never grown to encode a *refinement* of an existing member — that is what `reason` is
    for.
- `Passage` and `Citation` gain `entry_location`; `AnswerEnvelope` gains `reason`,
  `retry_after`, `detail`, `framing`, `causes[]`, `required_manual` and `scope_dropped[]`.
  Each has a named consumer criterion, so none repeats the produced-but-unconsumed defect
  the amendment exists to close.
- All four specs reconciled against the amended contract — 10 new criteria across
  `api/answer-engine` (111), `ui/ask-and-source-picker` (154) and `data/manual-corpus` (83).
- The triage sidecar now lives at `views/<hex>/reports/<slug>.json`, inside the view, so it
  and the passages it keys always share a revision. Ingestion audits stay at
  `index/audits/<slug>.json`: an audit describes a *run* and must outlive the view it
  accompanied, whereas a sidecar describes *the passages in a view*. The run-side directory
  is renamed to avoid two files at the same basename differing only in parent, which fails
  silently rather than erroring. This discharges the blocking prerequisite on the answer
  engine (manual-corpus Decision 8).

### Added

- `ui/ask-and-source-picker` design and decision log (7 ADRs) — the fourth and last design.
  A SvelteKit SPA served same-origin by the answer-engine process; append-only streaming
  with block type fixed by a block's first line (4.2); one window-level keyboard router
  owning the 1–4 arming rule (1.11); numeric citation markers with detail in a list, so
  CONTRACTS §3's five inline obligations fit inside the 25-word reading budget (11.7).
- `data/manual-corpus` criteria 8.8–8.11 defining what "a queryable index" means — both
  kinds of matching over the same passages, every `Passage` and `SourceRecord` field
  readable without a source PDF, restriction to a chosen subset of sources, and
  self-describing artefacts. Closes the requirements gap that design named as defect 3.
- `api/answer-engine` decision log entries 8–10: count the history token budget locally
  rather than with a provider endpoint; build narrowing candidates in the engine from the
  triage entry rather than from model output; filter triage fix pointers through the turn's
  source scope, carrying an out-of-scope cause as `unbacked`.
- A *Requirements defects to reconcile* section in the `api/answer-engine` design, matching
  its two sibling designs. Six open contract defects, each found from both ends of its seam.

### Fixed

- `api/answer-engine` design, repaired against two independent reviews:
  - History token counting used `client.messages.count_tokens`, a provider HTTP endpoint —
    an unbudgeted round trip inside the 150 ms engine-overhead cap that also broke 6.14's
    no-outbound-request guarantee on a local provider and bypassed 6.15's disclosure gate.
  - Triage fix pointers were admitted to the grounding set with no scope check, so a
    triage-only scope injected passages from deselected sources, breaking 1.1, 2.4 and 5.1
    and corrupting `contributing_sources[]`.
  - The triage sidecar was read as `authored-triage.json`; the corpus writes
    `authored_triage.json`. `data/symptom-triage` names this exact spelling as a silent
    failure leaving every entry in scope for every turn. Now derived by the slug rule and
    failing loudly when absent.
  - `incomplete` was unreachable: a mid-stream failure matched the "any other provider
    error" gate first. Gates are now split pre-flight and in-flight, with "has any output
    been streamed" evaluated ahead of every error-kind gate.
  - The loopback `Origin` guard rejected the browser surface's own origin. Resolved by
    serving the built surface same-origin, with the dev proxy rewriting `Origin` as well
    as `Host`.
  - Retrieval masked after top-k rather than before it; the lexical relevance arm and
    per-source qualification were global, so a small guide beside the 1009-page Live manual
    could never fire 5.6's floor.
  - Device scope had no defined value for the `authored-triage` source, so a triage-only
    turn filtered out its whole starter set.
  - `GET /passages/{id}` read a stale view after a re-ingest, breaching 3.5.
  - Outcome arithmetic: sixteen outcomes, ten engine-determined and six content — not
    seventeen and eleven — in both the design and Decision 3.
  - The 3.7 ungrounded rule missed uncited procedure steps, which 3.1 counts as substantive.
  - `timings` carried a parser status; `framing` is now its own event and `timings` carries
    the five stages 4.11 names.
  - Dangling `§Outcome` reference, and the inverted claim that the state timeout was the
    shortest member of the `asyncio.gather`.
- `specs/OVERVIEW.md` regenerated: it still recorded all four specs as "requirements
  complete, design not started" when three designs existed.

### Added

- DAWMans MVP requirements: four specs totalling 398 anchored EARS criteria —
  `data/manual-corpus` (vendor PDF ingestion into a citable corpus),
  `data/symptom-triage` (an authored symptom-to-cause source), `api/answer-engine`
  (retrieval, grounding, providers, the `StateSource` seam) and
  `ui/ask-and-source-picker` (the localhost browser surface).
- `specs/CONTRACTS.md` — governing shared contracts for the spec seams: the
  `SourceRecord`, `Passage`, `Citation` and `AnswerEnvelope` records, a closed outcome
  taxonomy, and a composed end-to-end latency budget.
- `specs/DECISIONS.md` (9 ADRs) and a generated `specs/OVERVIEW.md` index.
- Research notes in `docs/agent-notes/` for Ableton state integration and the retrieval
  approach, both verified by measurement on the target machine.
- `manuals/` for the reference PDFs, with the filename convention documented; the PDFs
  themselves are gitignored as third-party and not redistributable.

### Added (template)

- Machine entry points for external tools such as sdd-ui (`specs/template-refinement/prd.md`):
  `tools/new_project.sh` / `make new-project` for non-interactive project creation from the
  template (placeholder filling, `nextup.md` intent seeding, git init, optional worked-example
  removal), and `tools/status.sh` / `make status` for a plain-English or `--json` summary of
  where a project stands.

### Changed

- `nextup.example.md` now uses the canonical `<!-- USER -->` / `<!-- LM -->` zone markers and
  documents the `act autonomously` flag; README gained a "Machine entry points" section.
